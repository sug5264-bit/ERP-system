# --- deps stage -----------------------------------------------------------
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
# Use ci when a lockfile is present, fall back to install otherwise.
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi


# --- builder stage --------------------------------------------------------
FROM node:20-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Build a production bundle. Public env (`NEXT_PUBLIC_*`) is baked in at
# build time and must be supplied at build, not at runtime.
ARG NEXT_PUBLIC_API_BASE=""
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
RUN npm run build


# --- runtime stage --------------------------------------------------------
FROM node:20-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000

# Non-root user.
RUN addgroup -S erp && adduser -S erp -G erp

# Bring only what `next start` needs.
COPY --from=builder --chown=erp:erp /app/package.json ./package.json
COPY --from=builder --chown=erp:erp /app/node_modules ./node_modules
COPY --from=builder --chown=erp:erp /app/.next ./.next
COPY --from=builder --chown=erp:erp /app/public ./public
COPY --from=builder --chown=erp:erp /app/next.config.mjs ./next.config.mjs

USER erp
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://127.0.0.1:3000/login || exit 1

CMD ["npm", "run", "start"]
