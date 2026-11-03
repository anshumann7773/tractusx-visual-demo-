# Builds the EDC sample connectors and runs BOTH of them (Bob + Alice)
# inside one container, so they reach each other on "localhost"
# exactly like the official samples expect.
#
# Built by ./setup.sh from the EDC Samples repo, pinned to the last version
# that still contains the transfer samples (they were removed on 14 Oct 2026).

# ---- Stage 1: build both connectors with Java + Gradle (only inside Docker) ----
FROM eclipse-temurin:21-jdk AS build
WORKDIR /src
COPY . .
# Small change to the sample's proxy data plane: also forward the query string
# (?assetIds=...), so the KIT's registry lookup GET /lookup/shells?assetIds=...
# works through the connector. Without it the demos fall back to listing all twins.
RUN F=transfer/transfer-03-consumer-pull/provider-proxy-data-plane/src/main/java/org/eclipse/edc/sample/extension/proxy/ProxyController.java \
 && sed -i 's|var targetUrl = sourceDataAddress.getStringProperty(EDC_NAMESPACE + "baseUrl") + "/" + requestContext.getUriInfo().getPath();|var rawQuery = requestContext.getUriInfo().getRequestUri().getRawQuery();\n            var targetUrl = sourceDataAddress.getStringProperty(EDC_NAMESPACE + "baseUrl") + "/" + requestContext.getUriInfo().getPath() + (rawQuery == null ? "" : "?" + rawQuery);|' "$F" \
 && (grep -q rawQuery "$F" && echo "proxy: query forwarding enabled" || echo "proxy: unchanged")
RUN chmod +x ./gradlew && ./gradlew --no-daemon \
      transfer:transfer-00-prerequisites:connector:build \
      transfer:transfer-03-consumer-pull:provider-proxy-data-plane:build \
      -x test -x checkstyleMain -x checkstyleTest

# ---- Stage 2: small image that just runs the two connectors ----
FROM eclipse-temurin:21-jre
WORKDIR /app

# Alice (consumer): the basic connector from transfer-00
COPY --from=build /src/transfer/transfer-00-prerequisites/connector/build/libs/connector.jar consumer.jar
COPY --from=build /src/transfer/transfer-00-prerequisites/resources/configuration/consumer-configuration.properties consumer.properties

# Bob (provider): the connector with the HTTP proxy data plane from transfer-03
COPY --from=build /src/transfer/transfer-03-consumer-pull/provider-proxy-data-plane/build/libs/connector.jar provider.jar
COPY --from=build /src/transfer/transfer-03-consumer-pull/resources/configuration/provider.properties provider.properties

# Keep memory small so it runs fine on an 8 GB Mac
ENV JAVA_TOOL_OPTIONS="-Xmx512m"

# Bob (provider): 19193 management, 19194 protocol, 19291 public data plane
# Alice (consumer): 29193 management, 29194 protocol, 29291 public data plane
EXPOSE 19193 19194 19291 29193 29194 29291

# Bob runs in the background (log: /app/provider.log), Alice in the foreground
CMD ["sh", "-c", "java -Dedc.fs.config=provider.properties -jar provider.jar > /app/provider.log 2>&1 & exec java -Dedc.fs.config=consumer.properties -jar consumer.jar"]
