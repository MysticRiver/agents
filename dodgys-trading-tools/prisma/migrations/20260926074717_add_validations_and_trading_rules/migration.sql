-- AlterTable
ALTER TABLE "Settings" ADD COLUMN "tradingRules" TEXT;

-- CreateTable
CREATE TABLE "Validation" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "userId" TEXT NOT NULL,
    "date" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "instrument" TEXT NOT NULL,
    "direction" TEXT NOT NULL,
    "setupType" TEXT NOT NULL,
    "checklist" TEXT NOT NULL,
    "emotionalState" INTEGER NOT NULL,
    "entryPrice" REAL,
    "stopLoss" REAL,
    "takeProfit" REAL,
    "session" TEXT,
    "isRevengeTrade" BOOLEAN NOT NULL DEFAULT false,
    "isLightBulbTrade" BOOLEAN NOT NULL DEFAULT false,
    "tradesCountToday" INTEGER,
    "isInLossToday" BOOLEAN,
    "screenshot" TEXT,
    "notes" TEXT,
    "score" INTEGER NOT NULL,
    "grade" TEXT NOT NULL,
    "scoreBreakdown" TEXT NOT NULL,
    "feedback" TEXT NOT NULL,
    "tradeTaken" BOOLEAN,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Validation_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);
