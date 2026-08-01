/**
 * GitHub Pages public viewer settings (no secrets).
 * SNAPSHOT_URL: Supabase Storage public-viewer/snapshots/latest.json public URL
 *
 * SHOW_CAST_ICONS:
 *   true  … 「登場人物の役割説明」にピクトグラムを表示（現行）
 *   false … 旧テキストのみ表示に戻す（いつでも切替可）
 *
 * PRE_RACE_TRIGGER_MODE:
 *   "15" … サイドバー「主な更新タイミング」の直前行を15分前帯に
 *   "6_8" … 6〜8分前帯に
 */
window.PUBLIC_VIEWER_CONFIG = {
  SNAPSHOT_URL: "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/snapshots/latest.json",
  LINE_FRIEND_URL: "https://lin.ee/YOUR_LINE_OA",
  DISCORD_INVITE_URL: "https://discord.gg/WxEPbtSXS",
  BRAND_NAME: "\u7AF6\u99ACAI \u30DF\u30B9\u30C6\u30EA\u30FC\u4E88\u60F3",
  POLL_INTERVAL_MS: 30000,
  SHOW_CAST_ICONS: true,
  PRE_RACE_TRIGGER_MODE: "15",
  /**
   * 管理画面 API。空なら ADMIN_API_DISCOVERY_URL から base_url を取得。
   * パスワードはここへ書かない（サーバー .env の ADMIN_PANEL_PASSWORD）。
   */
  ADMIN_API_BASE_URL: "",
  ADMIN_API_DISCOVERY_URL:
    "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/admin_api.json",

  // --- BEGIN TEMP: TENKAI_SIM_LAUNCH (後から削除予定) ---
  /**
   * 管理画面「展開シミュレーション起動」を出すか。
   * false にすればメニュー非表示（コード削除までの簡易オフ）。
   */
  SHOW_TENKAI_SIM_LAUNCH: true,
  /**
   * 別タブで開く URL テンプレート。
   * 使える置換: {race_id} {place}/{venue} {R}/{race_no} {schedule_date}/{kaisai_date}
   * 空文字のとき: discovery JSON の tenkai_sim_url_template →
   *   tenkai_sim_base_url → ADMIN API base + "/tenkai?race_id={race_id}"
   * LAN 導入: tools/yokuumakun_tenkai_sim_launch/deploy_from_windows.ps1
   *   → discovery に tenkai_sim_url_template が入り、ここは空のままでよい。
   */
  TENKAI_SIM_URL_TEMPLATE: "",
  // --- END TEMP: TENKAI_SIM_LAUNCH ---
};
