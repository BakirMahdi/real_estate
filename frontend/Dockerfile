FROM node:22-alpine AS build

WORKDIR /app

# Trust any locally-provided extra CA certs (e.g. antivirus HTTPS-scanning
# roots) so `npm install` works on machines where HTTPS traffic is
# intercepted. The certs/ dir is machine-specific and gitignored; on
# machines that don't need this it's empty (besides .gitkeep), which
# produces an empty bundle below and is a no-op for Node.
COPY certs/ /app/certs/
RUN cat /app/certs/*.crt > /app/certs/extra-ca-bundle.pem 2>/dev/null; true
ENV NODE_EXTRA_CA_CERTS=/app/certs/extra-ca-bundle.pem

COPY package.json ./
RUN npm install

COPY . .
RUN npm run build

FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
