# TruthPixel reviewer dashboard — production image.
# Build from the repo root: docker build -f dashboard/Dockerfile -t truthpixel-dashboard .
#
# NEXT_PUBLIC_* vars are inlined into the client JS bundle at BUILD time -- must be passed as
# --build-arg, not just runtime env vars. TRUTHPIXEL_DASHBOARD_API_KEY / TRUTHPIXEL_API_URL
# are server-only and ARE read at runtime (app/api/_lib/backend.ts), not baked into the image
# -- set those on whatever platform runs this container, not as build args.
FROM node:20-slim AS base

WORKDIR /app

COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci

COPY dashboard/ ./

ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_SUPABASE_URL=${NEXT_PUBLIC_SUPABASE_URL}
ENV NEXT_PUBLIC_SUPABASE_ANON_KEY=${NEXT_PUBLIC_SUPABASE_ANON_KEY}

RUN npm run build

ENV NODE_ENV=production
EXPOSE 3001
# Cloud Run injects $PORT -- next start honors it via -p.
CMD ["sh", "-c", "npm start -- -p ${PORT:-3001}"]
