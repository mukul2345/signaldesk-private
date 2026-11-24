import type { Candidate, MarketIndex } from "../domain/types";

export const marketIndices: readonly MarketIndex[] = [
  { id: "nifty", name: "NIFTY 50", value: 26_103.4, changePercent: 0.68, direction: "up", status: "Bullish", points: [18, 24, 21, 30, 26, 35, 39, 44, 42, 51] },
  { id: "sensex", name: "SENSEX", value: 85_231.8, changePercent: 0.57, direction: "up", status: "Bullish", points: [22, 19, 25, 24, 31, 29, 35, 37, 41, 46] },
  { id: "midcap", name: "NIFTY MIDCAP", value: 61_442.2, changePercent: 0.21, direction: "up", status: "Constructive", points: [28, 29, 26, 31, 30, 32, 31, 35, 33, 36] },
  { id: "it", name: "NIFTY IT", value: 36_908.6, changePercent: -0.34, direction: "down", status: "Weak", points: [46, 43, 45, 39, 41, 36, 38, 32, 34, 29] }
];

export const candidates: readonly Candidate[] = [
  { id: "cdsl", rank: 1, symbol: "CDSL", company: "Central Depository Services", sector: "Financial Services", price: 1_742.5, changePercent: 2.42, score: 89, state: "READY", setup: "Volatility squeeze breakout", volumeRatio: 2.1, entry: 1_748, stop: 1_697, targetOne: 1_799, targetTwo: 1_850, probability: null, reasons: ["Price above 20D and 50D trend", "Volume expansion at 2.1× average", "Financial sector aligned with market"], contradictions: ["Near short-term resistance"] },
  { id: "bel", rank: 2, symbol: "BEL", company: "Bharat Electronics", sector: "Defence", price: 468.3, changePercent: 1.76, score: 86, state: "READY", setup: "20-day range breakout", volumeRatio: 1.8, entry: 470, stop: 456, targetOne: 484, targetTwo: 498, probability: null, reasons: ["Higher-high price structure", "Relative strength versus Nifty", "Healthy delivery-volume proxy"], contradictions: ["Sector is extended over five sessions"] },
  { id: "tatapower", rank: 3, symbol: "TATAPOWER", company: "Tata Power Company", sector: "Power", price: 392.75, changePercent: 1.08, score: 81, state: "WATCH", setup: "Trend pullback", volumeRatio: 1.3, entry: 397, stop: 384, targetOne: 410, targetTwo: 423, probability: null, reasons: ["Pullback held the 20D average", "Momentum recovered above neutral", "Power index remains constructive"], contradictions: ["Entry trigger has not fired", "Volume confirmation is moderate"] },
  { id: "maxhealth", rank: 4, symbol: "MAXHEALTH", company: "Max Healthcare Institute", sector: "Healthcare", price: 1_214.9, changePercent: 0.84, score: 78, state: "WATCH", setup: "Ascending base", volumeRatio: 1.4, entry: 1_223, stop: 1_184, targetOne: 1_262, targetTwo: 1_301, probability: null, reasons: ["Tight price base", "Defensive sector strength", "Accumulation pressure proxy positive"], contradictions: ["Historical sample below confidence threshold"] },
  { id: "persistent", rank: 5, symbol: "PERSISTENT", company: "Persistent Systems", sector: "Information Technology", price: 6_184, changePercent: -0.62, score: 58, state: "AVOID", setup: "Failed continuation", volumeRatio: 0.8, entry: 6_270, stop: 6_055, targetOne: 6_485, targetTwo: 6_700, probability: null, reasons: ["Long-term trend remains positive"], contradictions: ["Nifty IT is weak", "Breakout lost on low participation", "Fresh entry is outside permitted band"] }
];

export const accountMetrics = {
  availableCash: 50_000,
  deployed: 0,
  openRisk: 0,
  todayPnl: 0
} as const;
