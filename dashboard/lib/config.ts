export const config = {
  meta: {
    accessToken: process.env.META_ACCESS_TOKEN!,
    adAccountId: process.env.META_AD_ACCOUNT_ID!,
    apiVersion: "v21.0",
    baseUrl: "https://graph.facebook.com/v21.0",
  },
  supabase: {
    url: process.env.NEXT_PUBLIC_SUPABASE_URL!,
    anonKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    serviceRoleKey: process.env.SUPABASE_SERVICE_ROLE_KEY,
  },
  frontEndPrice: parseFloat(process.env.FRONT_END_PRICE || "29.99"),
} as const;
