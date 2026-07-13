# TruthPixel public webapp — production image.
# Build from the repo root: docker build -f webapp/Dockerfile -t truthpixel-webapp .
#
# NEXT_PUBLIC_* vars are inlined into the client JS bundle at BUILD time, not read at
# container-start time -- they must be passed as --build-arg, not just runtime env vars on
# whatever platform runs this image. A rebuild is required to change them.
FROM node:20-slim AS base

WORKDIR /app

COPY webapp/package.json webapp/package-lock.json ./
RUN npm ci

COPY webapp/ ./

ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_SUPABASE_URL=${NEXT_PUBLIC_SUPABASE_URL}
ENV NEXT_PUBLIC_SUPABASE_ANON_KEY=${NEXT_PUBLIC_SUPABASE_ANON_KEY}

RUN npm run build

ENV NODE_ENV=production
EXPOSE 3000
# Cloud Run injects $PORT -- next start honors it via -p.
CMD ["sh", "-c", "npm start -- -p ${PORT:-3000}"]
