import type { DashboardConfig } from "../domain/types";

export const dashboardConfig: DashboardConfig = {
  currency: "INR",
  locale: "en-IN",
  mode: "PAPER",
  dataLabel: "DEMO DATA",
  marketStatus: "Market closed",
  nextScan: "Monday · 09:20 IST",
  sourceFreshness: "Illustrative snapshot",
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? "/api"
};

export const formatMoney = (value: number) =>
  new Intl.NumberFormat(dashboardConfig.locale, {
    style: "currency",
    currency: dashboardConfig.currency,
    maximumFractionDigits: 0
  }).format(value);

export const formatNumber = (value: number) =>
  new Intl.NumberFormat(dashboardConfig.locale, { maximumFractionDigits: 2 }).format(value);

export const formatDateTime = (value: string) =>
  new Intl.DateTimeFormat(dashboardConfig.locale, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kolkata"
  }).format(new Date(value));
