import { routes, type VercelConfig } from "@vercel/config/v1";

const apiOrigin = process.env.TRAZIA_API_ORIGIN?.trim().replace(/\/+$/, "");
const ngrok = apiOrigin && /^https:\/\/[^/:]+\.ngrok-free\.(?:app|dev)$/i.test(apiOrigin);

export const config: VercelConfig = apiOrigin
  ? routes.route({
      src: "^/api/trazia/(.+)$",
      dest: `${apiOrigin}/$1`,
      transforms: ngrok ? [{
        type: "request.headers",
        op: "set",
        target: { key: "ngrok-skip-browser-warning" },
        args: "1",
      }] : undefined,
    }).getConfig()
  : {};
