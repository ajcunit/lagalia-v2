# Contenidor de desenvolupament (perfil "app" del compose).
# El build de producció (nginx/Caddy) arriba amb el desplegament.
FROM node:22-alpine

WORKDIR /srv/app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
