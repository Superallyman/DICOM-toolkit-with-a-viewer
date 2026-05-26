# ---------- deps stage (cache npm ci) ----------
FROM node:20-bullseye-slim AS deps
WORKDIR /app

# only package files for better caching
COPY package*.json ./
RUN npm ci

# ---------- build stage ----------
FROM node:20-bullseye-slim AS build
WORKDIR /app

# reuse cached deps
COPY --from=deps /app/node_modules ./node_modules
# app source (root has pages/, public/, components/, etc.)
COPY . .

# Public API URL for client-side (override via --build-arg)
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ARG NEXT_PUBLIC_OHIF_BASE_URL=http://localhost:8000/v1/viewer
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_OHIF_BASE_URL=$NEXT_PUBLIC_OHIF_BASE_URL
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# ---------- runtime stage ----------
FROM node:20-bullseye-slim AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
    NEXT_PUBLIC_OHIF_BASE_URL=http://localhost:8000/v1/viewer

# prod deps only
COPY package*.json ./
RUN npm ci --omit=dev

# app artifacts
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public

EXPOSE 3000
CMD ["npm", "run", "start", "--", "-p", "3000"]
