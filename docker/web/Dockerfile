# Stage 1: build
FROM node:20-alpine AS build
WORKDIR /app
COPY web/package*.json ./
RUN npm ci --prefer-offline
COPY web/ ./

# Build-time env vars — Vite bakes these as static strings into the bundle.
# VITE_BASE_URL: URL prefix the app is served under (/ for dev, /snipe for cloud)
# VITE_API_BASE: prefix for all /api/* fetch calls (empty for dev, /snipe for cloud)
ARG VITE_BASE_URL=/
ARG VITE_API_BASE=
ENV VITE_BASE_URL=$VITE_BASE_URL
ENV VITE_API_BASE=$VITE_API_BASE

RUN npm run build

# Stage 2: serve
FROM nginx:alpine
COPY docker/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
