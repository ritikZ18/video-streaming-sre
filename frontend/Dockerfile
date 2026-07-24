FROM node:20-alpine AS deps

WORKDIR /app

COPY package*.json ./
RUN npm ci

FROM node:20-alpine AS build

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY package*.json ./
COPY . .
RUN npm run build

FROM node:20-alpine

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1
WORKDIR /app

COPY package*.json ./
RUN apk upgrade --no-cache \
 && npm ci --omit=dev \
 && npm cache clean --force \
 && rm -rf /usr/local/lib/node_modules/npm \
    /usr/local/bin/npm \
    /usr/local/bin/npx \
    /opt/yarn-* \
    /usr/local/bin/yarn \
    /usr/local/bin/yarnpkg
COPY next.config.mjs ./
COPY --from=build /app/.next ./.next

EXPOSE 80

CMD ["node", "node_modules/next/dist/bin/next", "start", "-p", "80"]
