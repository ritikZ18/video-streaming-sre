FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM node:20-alpine

ENV NODE_ENV=production
WORKDIR /app

COPY --from=build /app ./

EXPOSE 80

CMD ["npm", "run", "start", "--", "-p", "80"]

