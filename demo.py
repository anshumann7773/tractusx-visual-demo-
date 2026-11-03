"""
Tractus-X live demo: Bob (supplier) shares part data with Alice (car maker),
the Catena-X way: find the digital twin first, then get the data.

Usage (normally started by ./run-demo.sh):
    .venv/bin/python demo.py              # simple output, for the audience
    .venv/bin/python demo.py --details    # also shows the technical details (JSON, IDs)
    .venv/bin/python demo.py /path/to/Samples
"""

import json
import re
import sys
import time
import uuid
from pathlib import Path

import requests

try:
    import dashboard  # live browser view (dashboard.py + dashboard.html, same folder)
except ImportError:
    dashboard = None

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
DETAILS = "--details" in sys.argv

SAMPLES = Path(ARGS[0]).expanduser() if ARGS else Path(__file__).resolve().parent / "Samples"
API = "v3"  # change to "v4" if the sample READMEs use /management/v4

BOB = f"http://localhost:19193/management/{API}"     # Bob's connector (management)
ALICE = f"http://localhost:29193/management/{API}"   # Alice's connector (management)
DTR = "http://localhost:4243/api/v3"                 # Bob's Tractus-X registry, seen from the Mac
DTR_FROM_CONNECTOR = "http://dtr:4243/api/v3"        # same registry, seen from Bob's connector
BOB_DSP = "http://localhost:19194/protocol"          # Bob's dataspace protocol address
BOB_PUBLIC = "http://localhost:19291/public"         # Bob's data plane

PARTDATA_FROM_CONNECTOR = "http://partdata:8080"   # Bob's part data server, seen from Bob's connector

DTR_TYPE = "https://w3id.org/catenax/taxonomy#DigitalTwinRegistry"
DTR_ASSET_ID = "digital-twin-registry"
PART_NUMBER = "BD-4711"
TOTAL_STEPS = 8

NEGOTIATION_DIR = SAMPLES / "transfer" / "transfer-01-negotiation" / "resources"
PULL_DIR = SAMPLES / "transfer" / "transfer-03-consumer-pull" / "resources"
HEADERS = {"Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Simple printing for the audience
# ---------------------------------------------------------------------------
class C:
    BOLD = "\033[1m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    GREY = "\033[90m"
    END = "\033[0m"


LINE = "─" * 64
CURRENT_STEP = 0


def emit(kind, **data):
    """Send an event to the live dashboard in the browser (if it is running)."""
    if dashboard:
        dashboard.emit(kind, **data)


def act(title):
    print(f"\n\n{C.BOLD}{'═' * 64}\n  {title}\n{'═' * 64}{C.END}")


# ---------------------------------------------------------------------------
# KIT views per step: which Tractus-X KIT the step comes from, and how it looks
# to a developer (Development view) and to IT (Operation view).
# The Adoption view is the step's spoken sentence. Lines starting with '#'
# are shown as quiet explanations.
# ---------------------------------------------------------------------------
KITS_USED = ["Connector KIT", "Digital Twin KIT", "Industry Core KIT", "Data Governance KIT"]

KIT_INFO = {
    1: ("Digital Twin KIT",
        ["POST http://localhost:4243/api/v3/shell-descriptors",
         "# a digital twin in the AAS 3.0 format: part number BD-4711 + where its data is"],
        ["Container 'dtr': Tractus-X Digital Twin Registry 0.13.0, port 4243",
         "Container 'postgres': the registry's database (not reachable from outside)"]),
    2: ("Connector KIT",
        ["POST http://localhost:19193/management/v3/assets   → 'brake-disc-data'",
         "POST http://localhost:19193/management/v3/assets   → 'digital-twin-registry'",
         "# the registry is labelled with the Catena-X type DigitalTwinRegistry"],
        ["Bob's connector, management API on port 19193",
         "Offers point inside Docker: http://partdata:8080 and http://dtr:4243"]),
    3: ("Connector KIT · rules: Data Governance KIT",
        ["POST http://localhost:19193/management/v3/policydefinitions",
         "POST http://localhost:19193/management/v3/contractdefinitions",
         "# policy = the rules; contract definition = rules + offers, now visible"],
        ["Bob's connector (control plane), port 19193",
         "Rules are stored in memory: a fresh start forgets them"]),
    4: ("Digital Twin KIT · Connector KIT",
        ["POST http://localhost:29193/management/v3/catalog/request",
         "# Alice's connector asks Bob's over the Dataspace Protocol (2025-1)",
         "# then: find the offer with type …/catenax/taxonomy#DigitalTwinRegistry"],
        ["Alice's connector (port 29193) → Bob's protocol endpoint (port 19194)",
         "Connector to connector only: no central server in between"]),
    5: ("Connector KIT",
        ["POST http://localhost:29193/management/v3/contractnegotiations",
         "GET  …/contractnegotiations/{id}   until state = FINALIZED",
         "# result: a contract agreement ID"],
        ["Protocol endpoints: Alice 29194 ↔ Bob 19194",
         "Both connectors negotiate automatically, machine to machine"]),
    6: ("Digital Twin KIT · Industry Core KIT",
        ["POST …/transferprocesses  (HttpData-PULL)  →  GET …/edrs/{id}/dataaddress",
         "GET  http://localhost:19291/public/shell-descriptors   + temporary key",
         "# the twin's subprotocolBody says: id=brake-disc-data"],
        ["Bob's data plane, port 19291 → container 'dtr' (port 4243 inside Docker)",
         "The key (EDR) works only for this contract, for a short time"]),
    7: ("Connector KIT",
        ["POST http://localhost:29193/management/v3/contractnegotiations",
         "# same as step 5, now for the offer 'brake-disc-data'"],
        ["Protocol endpoints: Alice 29194 ↔ Bob 19194"]),
    8: ("Connector KIT",
        ["POST …/transferprocesses  (HttpData-PULL)  →  GET …/edrs/{id}/dataaddress",
         "GET  http://localhost:19291/public/   + temporary key",
         "# Bob's data plane checks the key, then fetches brake-disc.json"],
        ["Bob's data plane, port 19291 → container 'partdata' (port 8080 inside Docker)",
         "'partdata' has no port to the outside: the connector is the only way in"]),
}

VIEW_KEYS = {"a": "adoption", "d": "development", "o": "operation",
             "1": "adoption", "2": "development", "3": "operation"}


def step(number, title, say, **extra):
    """extra = additional data for the live view, e.g. seq=[...] for a KIT sequence panel."""
    global CURRENT_STEP
    CURRENT_STEP = number
    kit, dev, ops = KIT_INFO.get(number, ("", [], []))
    print(f"\n{C.BLUE}{LINE}{C.END}")
    print(f"{C.BOLD}{C.BLUE}  STEP {number} of {TOTAL_STEPS}  ·  {title}{C.END}")
    print(f"{C.BLUE}{LINE}{C.END}")
    if kit:
        print(f"  📘 {kit}")
    print(f"{C.YELLOW}  🗣  {say}{C.END}")
    # the screen shows the step (and its KIT views) while you talk
    emit("step", n=number, title=title, say=say, kit=kit, dev=dev, ops=ops, **extra)
    while True:
        answer = input(f"{C.GREY}     (Enter = run  ·  a / d / o + Enter = Adoption / Development / Operation view){C.END} ")
        choice = VIEW_KEYS.get(answer.strip().lower())
        if choice:
            emit("view", view=choice)
            print(f"{C.GREY}     → browser shows the {choice.capitalize()} view{C.END}")
            continue
        break


def flow(picture, *moves):
    """Print a one-line picture of who talks to whom, and animate it in the browser.

    Each move is (from, to, icon, label). Node names: bob, registry, partdata,
    bobconn, aliceconn, alice.
    """
    if picture:
        print(f"\n     {picture}\n")
    for src, dst, icon, label in moves:
        emit("move", src=src, dst=dst, icon=icon, label=label)


def badge(node, text):
    """Add a small permanent label to a box in the browser, e.g. 'BD-4711'."""
    emit("badge", node=node, text=text)


def wait(message):
    print(f"  ⏳ {message}", flush=True)
    emit("wait", text=message)


def done(message):
    print(f"{C.GREEN}  ✅ {message}{C.END}")
    emit("done", n=CURRENT_STEP, text=message)


def details(label, data):
    """Technical output, only shown with --details."""
    if not DETAILS:
        return
    text = data if isinstance(data, str) else json.dumps(data, indent=2)
    lines = text.splitlines()
    if len(lines) > 20:
        lines = lines[:20] + [f"... ({len(lines) - 20} more lines)"]
    print(f"{C.GREY}     [details] {label}")
    for line in lines:
        print(f"     {line}")
    print(C.END, end="")


def problem(message):
    emit("error", text=message)
    time.sleep(1)  # give the browser a moment to show the error
    sys.exit(f"\n❌ {message}\n   Run again with more info:  .venv/bin/python demo.py --details")


# ---------------------------------------------------------------------------
# HTTP + JSON-LD helpers
# ---------------------------------------------------------------------------
def load(path, replacement=None):
    """Load a sample JSON body; replace any {{placeholder}} with the given value."""
    text = path.read_text()
    if replacement is not None:
        text = re.sub(r"\{\{[^}]+\}\}", replacement, text)
    return json.loads(text)


def field(obj, name):
    """Read a JSON-LD field: 'state', 'edc:state' or the full IRI."""
    if not isinstance(obj, dict):
        return None
    for key in (name, f"edc:{name}", f"https://w3id.org/edc/v0.0.1/ns/{name}"):
        if key in obj:
            return obj[key]
    return None


def as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def post(url, body):
    response = requests.post(url, json=body, headers=HEADERS, timeout=30)
    if response.status_code >= 400:
        print(f"⚠ {response.status_code}: {response.text[:500]}")
        if response.status_code == 409:
            problem("This was already created. Restart fresh with:  bash run-demo.sh")
        response.raise_for_status()
    return response.json() if response.text else {}


def get(url, headers=None):
    response = requests.get(url, headers=headers or HEADERS, timeout=30)
    response.raise_for_status()
    return response.json()


def wait_until(url, wanted_states, label):
    for _ in range(30):
        data = get(url)
        state = field(data, "state")
        details(f"{label} state", str(state))
        if state in wanted_states:
            return data
        if state in ("TERMINATED", "ERROR"):
            details(label, data)
            problem(f"{label} failed.")
        time.sleep(1)
    problem(f"{label} did not finish in time.")


def wait_for_services():
    print(f"\n{C.BOLD}Getting everything ready...{C.END}")
    checks = (
        ("🏭 Bob's connector", ("bob", "partdata", "bobconn"),
         lambda: requests.post(f"{BOB}/assets/request", json={}, headers=HEADERS, timeout=3)),
        ("🚗 Alice's connector", ("alice", "aliceconn"),
         lambda: requests.post(f"{ALICE}/assets/request", json={}, headers=HEADERS, timeout=3)),
        ("📒 Bob's Tractus-X registry", ("registry",),
         lambda: requests.get(f"{DTR}/shell-descriptors", timeout=3)),
    )
    for name, nodes, check in checks:
        for _ in range(90):
            try:
                check()  # any HTTP answer means the service is up
                print(f"{C.GREEN}  ✅ {name} is running{C.END}")
                for node in nodes:
                    emit("service", node=node, text=f"{name} is running")
                break
            except requests.exceptions.ConnectionError:
                time.sleep(2)
        else:
            problem(f"{name} is not reachable. Check with: docker compose logs")


# ---------------------------------------------------------------------------
# Reusable dataspace moves
# ---------------------------------------------------------------------------
def fetch_catalog():
    catalog = post(f"{ALICE}/catalog/request", load(NEGOTIATION_DIR / "fetch-catalog.json"))
    details("catalog", catalog)
    return as_list(catalog.get("dcat:dataset") or catalog.get("dataset"))


def find_dataset(datasets, predicate):
    for dataset in datasets:
        if predicate(dataset):
            return dataset
    return None


def offer_id_of(dataset):
    offer = as_list(dataset.get("odrl:hasPolicy") or dataset.get("hasPolicy"))[0]
    return offer["@id"]


def negotiate(dataset):
    """Accept the offer on a dataset; return the contract agreement ID."""
    body = load(NEGOTIATION_DIR / "negotiate-contract.json", offer_id_of(dataset))
    policy = body.get("policy", {})
    target_key = "target" if "target" in policy else "odrl:target"
    policy[target_key] = dataset["@id"]  # make sure we ask for THIS asset
    negotiation = post(f"{ALICE}/contractnegotiations", body)
    result = wait_until(f"{ALICE}/contractnegotiations/{negotiation['@id']}",
                        {"FINALIZED"}, "Negotiation")
    agreement_id = field(result, "contractAgreementId")
    details("contract agreement ID", agreement_id)
    return agreement_id


def get_key(agreement_id):
    """Start a pull transfer and return (endpoint, token) from the EDR."""
    transfer = post(f"{ALICE}/transferprocesses", load(PULL_DIR / "start-transfer.json", agreement_id))
    transfer_id = transfer["@id"]
    wait_until(f"{ALICE}/transferprocesses/{transfer_id}", {"STARTED", "COMPLETED"}, "Transfer")
    for _ in range(15):
        try:
            edr = get(f"{ALICE}/edrs/{transfer_id}/dataaddress")
            endpoint, token = field(edr, "endpoint"), field(edr, "authorization")
            details("key (EDR)", f"endpoint: {endpoint}\ntoken:    {token[:40]}...")
            return endpoint, token
        except requests.exceptions.HTTPError:
            time.sleep(1)
    problem("Alice did not receive a key.")


def part_card(part):
    """Print the brake disc data as a simple, readable card."""
    rows = (
        ("Part", part.get("partName")),
        ("Part number", part.get("manufacturerPartId")),
        ("Serial number", part.get("serialNumber")),
        ("Made by", part.get("manufacturer")),
        ("Made in", f"{part.get('madeIn')}, {part.get('productionDate')}"),
        ("Material", part.get("material")),
        ("Size / weight", f"{part.get('diameterMm')} mm, {part.get('weightKg')} kg"),
        ("CO₂ footprint", f"{part.get('carbonFootprintKgCO2e')} kg CO₂e"),
        ("Recyclable", "yes" if part.get("recyclable") else "no"),
    )
    print(f"\n     ┌{'─' * 50}┐")
    print(f"     │ {'📦 Data Alice received from Bob':<48}│")  # emoji is 2 columns wide
    print(f"     ├{'─' * 50}┤")
    for label, value in rows:
        print(f"     │ {label:<15}{str(value):<34}│")
    print(f"     └{'─' * 50}┘")


# ---------------------------------------------------------------------------
# The demo
# ---------------------------------------------------------------------------
def main():
    if not NEGOTIATION_DIR.exists():
        problem(f"Can't find the connector samples at {SAMPLES}. Run: bash setup.sh")

    print(f"\n{C.BOLD}🏭 Bob (supplier)  shares part data with  🚗 Alice (car maker){C.END}")
    print(f"{C.GREY}   using a Tractus-X Digital Twin Registry and two dataspace connectors{C.END}")
    url = dashboard.start() if dashboard else None
    if url:
        print(f"\n  🖥  Live view in your browser: {C.BOLD}{url}{C.END}  (opens by itself)")
    else:
        print(f"\n  {C.GREY}(Live browser view not available, the demo works without it){C.END}")
    wait_for_services()

    data_asset = {
        "@context": {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"},
        "@id": "brake-disc-data",
        "properties": {"name": "Brake disc BD-4711 part data", "contenttype": "application/json"},
        "dataAddress": {
            "type": "HttpData",
            "baseUrl": PARTDATA_FROM_CONNECTOR,
            "proxyPath": "true",
        },
    }
    data_asset_id = data_asset["@id"]
    twin_id = f"urn:uuid:{uuid.uuid4()}"

    # ===================== Act 1: Bob prepares =====================
    act("PART 1  ·  🏭 Bob, the supplier, gets ready")

    step(1, "Bob makes a digital twin of his part",
         "Bob writes his brake disc into his Tractus-X registry: a phonebook of his products.")
    shell = {
        "id": twin_id,
        "idShort": "BobsBrakeDisc",
        "globalAssetId": f"urn:uuid:{uuid.uuid4()}",
        "specificAssetIds": [{
            "name": "manufacturerPartId",
            "value": PART_NUMBER,
            "externalSubjectId": {
                "type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": "PUBLIC_READABLE"}],
            },
        }],
        "submodelDescriptors": [{
            "id": f"urn:uuid:{uuid.uuid4()}",
            "idShort": "PartDetails",
            "semanticId": {
                "type": "ExternalReference",
                # Simplified demo data model (not an official Catena-X aspect model)
                "keys": [{"type": "GlobalReference",
                          "value": "urn:samm:demo.bob:1.0.0#BrakeDiscInfo"}],
            },
            "endpoints": [{
                "interface": "SUBMODEL-3.0",
                "protocolInformation": {
                    "href": BOB_PUBLIC,
                    "endpointProtocol": "HTTP",
                    "endpointProtocolVersion": ["1.1"],
                    "subprotocol": "DSP",
                    # Tells Alice which connector asset holds the data
                    "subprotocolBody": f"id={data_asset_id};dspEndpoint={BOB_DSP}",
                    "subprotocolBodyEncoding": "plain",
                    "securityAttributes": [{"type": "NONE", "key": "NONE", "value": "NONE"}],
                },
            }],
        }],
    }
    flow("🏭 Bob  ──▶  📒 Registry      “Brake disc BD-4711 exists”",
         ("bob", "registry", "📝", "Brake disc BD-4711"))
    details("digital twin", post(f"{DTR}/shell-descriptors", shell))
    badge("registry", f"🔧 {PART_NUMBER}")
    done(f"Brake disc {PART_NUMBER} is now in Bob's registry")

    step(2, "Bob puts two things in his shop window",
         "Bob offers the part data, and also his registry, so others can look things up.")
    flow("🏭 Bob  ──▶  🚪 Bob's connector      “I offer: 📦 part data + 📒 registry”",
         ("bob", "bobconn", "📦", "Offer: part data"),
         ("bob", "bobconn", "📒", "Offer: registry"))
    details("part data asset", post(f"{BOB}/assets", data_asset))
    badge("bobconn", "📦 offer")
    badge("bobconn", "📒 offer")
    dtr_asset = {
        "@context": {"@vocab": "https://w3id.org/edc/v0.0.1/ns/", "dct": "http://purl.org/dc/terms/"},
        "@id": DTR_ASSET_ID,
        "properties": {
            "name": "Bob's Digital Twin Registry",
            "dct:type": {"@id": DTR_TYPE},
        },
        "dataAddress": {
            "type": "HttpData",
            "baseUrl": DTR_FROM_CONNECTOR,
            "proxyPath": "true",
            "proxyQueryParams": "true",
        },
    }
    details("registry asset", post(f"{BOB}/assets", dtr_asset))
    done("Bob now offers 2 things: 📦 part data and 📒 his registry")

    step(3, "Bob writes his rules",
         "Bob decides who may use his offers, and how. Nothing is shared without these rules.")
    flow("🏭 Bob  ──▶  📜 Rules      “Use only with a signed contract”",
         ("bob", "bobconn", "📜", "Rules"))
    details("policy", post(f"{BOB}/policydefinitions", load(NEGOTIATION_DIR / "create-policy.json")))
    details("contract definition",
            post(f"{BOB}/contractdefinitions", load(NEGOTIATION_DIR / "create-contract-definition.json")))
    badge("bobconn", "📜 rules")
    done("Bob's offers are now open, under his rules")

    # ===================== Act 2: Alice searches =====================
    act("PART 2  ·  🚗 Alice, the car maker, looks for the part")

    step(4, "Alice looks in Bob's shop window",
         "Alice doesn't know where Bob's data is. First she looks for his product phonebook.")
    flow("🚗 Alice  ──▶  🚪 Bob's connector      “What do you offer?”",
         ("alice", "aliceconn", "❓", "What does Bob offer?"),
         ("aliceconn", "bobconn", "❓", "What do you offer?"))
    datasets = fetch_catalog()
    dtr_dataset = find_dataset(datasets, lambda d: DTR_TYPE in json.dumps(d))
    if dtr_dataset is None:
        problem("Alice could not find Bob's registry in his shop window.")
    flow("", ("bobconn", "aliceconn", "📋", f"{len(datasets)} offers"),
         ("aliceconn", "alice", "📋", "Found: 📒 registry"))
    done(f"Alice sees {len(datasets)} offers, and finds Bob's 📒 registry")

    step(5, "Alice signs a contract to use the registry",
         "Even the phonebook is protected. Alice needs a contract before she may look inside.")
    flow("🚗 Alice  ◀──  📜  ──▶  🏭 Bob      the two connectors agree automatically",
         ("alice", "aliceconn", "📜", "I accept the rules"),
         ("aliceconn", "bobconn", "📜", "Contract request: registry"))
    wait("Bob's and Alice's connectors are negotiating...")
    dtr_agreement = negotiate(dtr_dataset)
    flow("", ("bobconn", "aliceconn", "✍️", "Contract signed"))
    badge("aliceconn", "✍️ contract 1")
    done("Contract signed ✍️")

    step(6, "Alice looks up the brake disc",
         "Alice gets a temporary key and reads Bob's registry. "
         "The entry tells her where the part data is.")
    wait("Alice is getting a temporary key 🔑 ...")
    endpoint, token = get_key(dtr_agreement)
    flow("🚗 Alice  ──🔑──▶  🚪 Bob's connector  ──▶  📒 Registry      “Where is BD-4711?”",
         ("bobconn", "aliceconn", "🔑", "Temporary key"),
         ("aliceconn", "alice", "🔑", "Key for the registry"),
         ("alice", "bobconn", "🔑", "Where is BD-4711?"),
         ("bobconn", "registry", "🔎", "Look up BD-4711"))
    twins = get(f"{endpoint.rstrip('/')}/shell-descriptors", headers={"Authorization": token})
    results = as_list(twins.get("result", twins))
    twin = next((t for t in results if t.get("id") == twin_id), results[0] if results else None)
    if twin is None:
        problem("Bob's registry returned no parts.")
    details("digital twin found", {k: twin.get(k) for k in ("id", "idShort", "specificAssetIds")})
    body = twin["submodelDescriptors"][0]["endpoints"][0]["protocolInformation"]["subprotocolBody"]
    asset_from_twin = dict(part.split("=", 1) for part in body.split(";"))["id"]
    details("data lives in connector asset", asset_from_twin)
    flow("", ("registry", "bobconn", "📍", "Data is in: part data offer"),
         ("bobconn", "alice", "📍", "Data is in: part data offer"))
    badge("alice", f"📍 {PART_NUMBER} found")
    done(f"Found brake disc {PART_NUMBER}, and where its data is 📍")

    # ===================== Act 3: Alice gets the data =====================
    act("PART 3  ·  🚗 Alice gets the part data")

    step(7, "Alice signs a contract for the part data",
         "Now Alice knows exactly what to ask for. She signs a second contract, for the data itself.")
    data_dataset = find_dataset(datasets, lambda d: d.get("@id") == asset_from_twin)
    if data_dataset is None:
        problem("The part data is not in Bob's shop window.")
    flow("🚗 Alice  ◀──  📜  ──▶  🏭 Bob      second contract, for the data",
         ("alice", "aliceconn", "📜", "I accept the rules"),
         ("aliceconn", "bobconn", "📜", "Contract request: part data"))
    wait("Bob's and Alice's connectors are negotiating...")
    data_agreement = negotiate(data_dataset)
    flow("", ("bobconn", "aliceconn", "✍️", "Contract signed"))
    badge("aliceconn", "✍️ contract 2")
    done("Contract signed ✍️")

    step(8, "Alice gets the data 🎉",
         "With a new temporary key, Alice gets the data directly from Bob. "
         "No central server in between.")
    wait("Alice is getting a temporary key 🔑 ...")
    endpoint, token = get_key(data_agreement)
    flow("🏭 Bob  ──📦──▶  🚗 Alice      directly, with a key that expires",
         ("bobconn", "aliceconn", "🔑", "Temporary key"),
         ("aliceconn", "alice", "🔑", "Key for the part data"),
         ("alice", "bobconn", "🔑", "Please send BD-4711 data"),
         ("bobconn", "partdata", "🔎", "Get BD-4711"))
    response = requests.get(endpoint, headers={"Authorization": token}, timeout=30)
    response.raise_for_status()
    try:
        part = response.json()
    except ValueError:
        details("data received", response.text[:1500])
        problem("Bob's part data was not readable.")
    details("data received", part)
    flow("", ("partdata", "bobconn", "📦", "Brake disc data"),
         ("bobconn", "alice", "📦", "Brake disc data"))
    done("Alice received the brake disc data from Bob")
    emit("part", part=part)
    part_card(part)

    print(f"\n{C.BOLD}{'═' * 64}")
    print("  That's Catena-X in one picture:")
    print("  📒 find the part  →  ✍️ contract  →  🔑 key  →  📦 data")
    print("  Bob kept control the whole time. 🏭")
    print(f"{'═' * 64}{C.END}\n")
    print(f"  📘 KITs in this demo: {' · '.join(KITS_USED)}\n")
    emit("finish", kits=KITS_USED)
    if url:
        input(f"{C.GREY}  (press Enter to close the live view){C.END}")


if __name__ == "__main__":
    main()
