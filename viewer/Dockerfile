FROM node:20-bullseye AS builder

RUN apt-get update && apt-get install -y git curl unzip

# install bun
RUN curl -fsSL https://bun.sh/install | bash
ENV PATH="/root/.bun/bin:$PATH"

WORKDIR /app

RUN git clone --depth 1 --branch v3.12.2 https://github.com/OHIF/Viewers.git ohif

WORKDIR /app/ohif

RUN bun install
RUN bun run build

FROM nginx:1.27-alpine

COPY --from=builder /app/ohif/platform/app/dist /usr/share/nginx/html
COPY ./infra/viewer/app-config.js /usr/share/nginx/html/
COPY ./infra/viewer/init-service-worker.js /usr/share/nginx/html/
COPY ./infra/viewer/sw.js /usr/share/nginx/html/
