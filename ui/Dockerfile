FROM node:20-alpine AS build
WORKDIR /app
ENV NODE_ENV=development
COPY package.json package-lock.json* ./
RUN npm ci --silent || npm install --silent
COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev"]
