FROM node:20-alpine AS build
WORKDIR /app
ARG VITE_API_URL
ARG VITE_OIDC_PROVIDER_LABEL
ARG VITE_APP_ORG_KEY
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_OIDC_PROVIDER_LABEL=$VITE_OIDC_PROVIDER_LABEL
ENV VITE_APP_ORG_KEY=$VITE_APP_ORG_KEY
COPY package.json package-lock.json* ./
RUN npm ci --include=optional && npm install @rollup/rollup-linux-x64-musl --save-optional
COPY . .
RUN NODE_ENV=production npm run build

FROM nginx:1.27-alpine AS runtime
RUN rm /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
