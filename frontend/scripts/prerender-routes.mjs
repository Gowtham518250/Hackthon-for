import { cp, mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";

const routes = [
  "login",
  "register",
  "check-email",
  "verify-email",
  "forgot-password",
  "verify-reset",
  "reset-password",
  "dashboard",
  "about",
];

const source = join(process.cwd(), "dist", "index.html");

for (const route of routes) {
  const target = join(process.cwd(), "dist", route, "index.html");
  await mkdir(dirname(target), { recursive: true });
  await cp(source, target);
}

console.log(`Created direct SPA entry points for ${routes.length} routes.`);
