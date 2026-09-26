import "dotenv/config";
import { defineConfig } from "prisma/config";
import path from "path";

export default defineConfig({
  schema: path.join(__dirname, "prisma/schema.prisma"),
  migrations: {
    path: path.join(__dirname, "prisma/migrations"),
  },
  datasource: {
    url: "file:./dev.db",
  },
});
