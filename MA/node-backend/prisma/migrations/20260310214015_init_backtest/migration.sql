-- CreateTable
CREATE TABLE "PriceData" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "symbol" TEXT NOT NULL,
    "timestamp" DATETIME NOT NULL,
    "open" REAL NOT NULL,
    "high" REAL NOT NULL,
    "low" REAL NOT NULL,
    "close" REAL NOT NULL,
    "volume" REAL NOT NULL
);

-- CreateTable
CREATE TABLE "ModelPrediction" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "symbol" TEXT NOT NULL,
    "model_name" TEXT NOT NULL,
    "prediction_date" DATETIME NOT NULL,
    "predicted_price" REAL NOT NULL,
    "actual_price" REAL,
    "mape" REAL,
    "direction_correct" BOOLEAN,
    "created_at" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- CreateIndex
CREATE UNIQUE INDEX "PriceData_symbol_timestamp_key" ON "PriceData"("symbol", "timestamp");
