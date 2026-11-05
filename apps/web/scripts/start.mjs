import { cpSync } from "node:fs";
cpSync(".next/static", ".next/standalone/.next/static", { recursive: true });
cpSync("public", ".next/standalone/public", { recursive: true });
process.env.PORT ||= "3102";
process.env.HOSTNAME = "0.0.0.0";
await import("../.next/standalone/server.js");
