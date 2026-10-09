# Build the static bundle, then serve it with nginx (no Node at runtime).
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
# The optional build secret `extra_ca` lets builds behind a TLS-inspecting proxy trust its CA.
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -f /run/secrets/extra_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/extra_ca; fi; \
    npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
