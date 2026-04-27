// Bilingual translations: Arabic (ar) and English (en)

export type Lang = 'ar' | 'en';

export const t: Record<string, Record<Lang, string>> = {
  // Navbar
  dashboard:        { ar: 'لوحة التحكم',    en: 'Dashboard' },
  createBot:        { ar: 'إنشاء بوت',       en: 'Create Bot' },

  running:          { ar: 'شغال',            en: 'Running' },
  stopped:          { ar: 'متوقف',           en: 'Stopped' },

  // KPIs
  assetCount:       { ar: 'عدد الأصول',      en: 'Assets' },

  // Buttons
  saving:           { ar: 'جاري الحفظ...',  en: 'Saving...' },
  addAsset:         { ar: '+ إضافة',         en: '+ Add' },
  createBotBtn:     { ar: 'حفظ وإنشاء البوت', en: 'Save & Create Bot' },
  cancelRebalance:  { ar: 'إلغاء',           en: 'Cancel' },

  // Settings
  botName:          { ar: 'اسم البوت',       en: 'Bot Name' },
  assetsAndAlloc:   { ar: 'الأصول والنسب',  en: 'Assets & Allocations' },
  rebalanceMode:    { ar: 'وضع إعادة التوازن', en: 'Rebalance Mode' },
  proportional:     { ar: 'نسبة مئوية',     en: 'Proportional' },
  timed:            { ar: 'زمني',            en: 'Timed' },
  manual:           { ar: 'يدوي',            en: 'Manual' },
  deviationThresh:  { ar: 'عتبة الانحراف',  en: 'Deviation Threshold' },
  frequency:        { ar: 'التكرار',         en: 'Frequency' },
  daily:            { ar: 'يومي',            en: 'Daily' },
  weekly:           { ar: 'أسبوعي',         en: 'Weekly' },
  monthly:          { ar: 'شهري',           en: 'Monthly' },
  hourUtc:          { ar: 'الساعة (UTC)',    en: 'Hour (UTC)' },
  investedUsdt:     { ar: 'المبلغ المستثمر (USDT)', en: 'Invested Amount (USDT)' },
  totalSum:         { ar: 'المجموع',         en: 'Total' },
  mustBe100:        { ar: '(يجب أن يساوي 100%)', en: '(must equal 100%)' },

  // Copy portfolio
  copyPortfolio:    { ar: 'نسخ محفظة',          en: 'Copy Portfolio' },
  copyBtn:          { ar: 'نسخ وإنشاء',           en: 'Clone & Create' },

  // Create bot
  createBotTitle:   { ar: 'إنشاء محفظة ذكية', en: 'Create Smart Portfolio' },
  createBotSubtitle:{ ar: 'Spot – MEXC Exchange', en: 'Spot – MEXC Exchange' },
  minRecommended:   { ar: 'الحد الأدنى الموصى به', en: 'Minimum recommended' },

  // Multi-portfolio
  myPortfolios:       { ar: 'محافظي',                    en: 'My Portfolios' },
  myPortfoliosDesc:   { ar: 'عرض وإدارة جميع المحافظ المحفوظة', en: 'View and manage all saved portfolios' },
  portfolioCount:     { ar: 'محفظة',                     en: 'portfolios' },
  noPortfolios:       { ar: 'لا توجد محافظ بعد',          en: 'No portfolios yet' },
  noPortfoliosDesc:   { ar: 'أنشئ محفظتك الأولى من تبويب "إنشاء بوت"', en: 'Create your first portfolio from the "Create Bot" tab' },
  buyAndActivate:     { ar: 'شراء وتفعيل',               en: 'Buy & Activate' },
  deletePortfolio:    { ar: 'حذف المحفظة',               en: 'Delete Portfolio' },
  confirmDelete:      { ar: 'تأكيد الحذف',               en: 'Confirm Delete' },
  cantDeleteActive:   { ar: 'لا يمكن حذف المحفظة النشطة', en: 'Cannot delete the active portfolio' },
  createdAt:          { ar: 'تاريخ الإنشاء',             en: 'Created' },

  // Portfolio rebalance actions
  rebalancePortfolio:    { ar: 'إعادة توازن',              en: 'Rebalance' },
  rebalanceType:         { ar: 'نوع إعادة التوازن',        en: 'Rebalance Type' },
  rebalanceMarketValue:  { ar: 'بالقيمة السوقية',          en: 'By Market Value' },
  rebalanceMarketDesc:   { ar: 'يعيد التوازن حسب النسب المحددة في المحفظة', en: 'Restore configured allocation targets' },
  rebalanceEqual:        { ar: 'بالتساوي',                 en: 'Equal Split' },
  rebalanceEqualDesc:    { ar: 'يوزع القيمة بالتساوي على جميع الأصول', en: 'Distribute value equally across all assets' },
  rebalanceConfirm:      { ar: 'تأكيد إعادة التوازن',      en: 'Confirm Rebalance' },
  rebalanceCancelBtn:    { ar: 'إلغاء',                    en: 'Cancel' },
  rebalanceRunning:      { ar: 'جاري إعادة التوازن...',    en: 'Rebalancing...' },
  rebalanceSuccess:      { ar: 'تمت إعادة التوازن بنجاح', en: 'Rebalance completed' },
  rebalanceCancelled:    { ar: 'تم إلغاء إعادة التوازن',  en: 'Rebalance cancelled' },
  activateFirst:         { ar: 'فعّل المحفظة أولاً لإعادة التوازن', en: 'Activate portfolio first to rebalance' },
  stopAndSell:           { ar: 'إيقاف وبيع المحفظة',               en: 'Stop & Sell Portfolio' },
  stopAndSellDesc:       { ar: 'سيتم إيقاف البوت وبيع جميع العملات إلى USDT', en: 'Bot will stop and all assets will be sold to USDT' },
  stopAndSellConfirm:    { ar: 'تأكيد الإيقاف والبيع',             en: 'Confirm Stop & Sell' },
  stopAndSellRunning:    { ar: 'جاري البيع...',                     en: 'Selling...' },
  stopAndSellSuccess:    { ar: 'تم إيقاف البوت وبيع المحفظة',      en: 'Bot stopped and portfolio sold' },
  stopAndSellCancel:     { ar: 'إلغاء',                             en: 'Cancel' },
  portfolioRunning:      { ar: 'شغّالة ✅',                         en: 'Running ✅' },

  // Errors / messages
  errDuplicate:     { ar: 'لا يمكن تكرار العملات', en: 'Duplicate coin symbols not allowed' },
  errSum:           { ar: 'مجموع النسب يجب أن يساوي 100%', en: 'Allocations must sum to 100%' },
  errSymbol:        { ar: 'أدخل رمز كل عملة', en: 'Enter a symbol for each coin' },
  errBotName:       { ar: 'أدخل اسم البوت', en: 'Enter a bot name' },
  errAssetCount:    { ar: 'عدد العملات يجب أن يكون بين 1 و 12', en: 'Asset count must be between 1 and 12' },
  errAmount:        { ar: 'أدخل مبلغ استثمار صحيح', en: 'Enter a valid investment amount' },
  successCreated:   { ar: 'تم إنشاء البوت وتشغيله بنجاح!', en: 'Bot created and started successfully!' },
  successRebalance: { ar: 'تم تنفيذ إعادة التوازن بنجاح', en: 'Rebalance executed successfully' },
  cancelledRebalance:{ ar: 'تم إلغاء عملية Rebalance', en: 'Rebalance cancelled' },
  errLoad:          { ar: 'خطأ في تحميل البيانات', en: 'Error loading data' },
  loadingData:      { ar: 'جاري التحميل...', en: 'Loading...' },
  cancelWindow:     { ar: 'يمكنك الإلغاء خلال', en: 'You can cancel within' },
  seconds:          { ar: 'ثانية',           en: 'seconds' },

  // Allocation modes
  allocAiBalance:   { ar: 'رصيد ذكي',        en: 'AI Balance' },
  allocEqual:       { ar: 'متساوي',           en: 'Equal' },
  allocMarketCap:   { ar: 'القيمة السوقية',   en: 'By Market Cap' },

  // Entry price
  entryPrice:       { ar: 'سعر الدخول (USDT)', en: 'Entry Price (USDT)' },
  entryPriceOpt:    { ar: 'اختياري',           en: 'optional' },

  // Timed intervals
  interval30m:      { ar: '30 دقيقة',          en: '30 min' },
  interval1h:       { ar: 'ساعة',              en: '1 Hour' },
  interval4h:       { ar: '4 ساعات',           en: '4 Hours' },
  interval8h:       { ar: '8 ساعات',           en: '8 Hours' },
  interval12h:      { ar: '12 ساعة',           en: '12 Hours' },
  interval1d:       { ar: 'يوم',               en: '1 Day' },
  timedModeDesc:    { ar: 'يعيد البوت التوازن على فترات زمنية ثابتة، بالشراء بسعر منخفض والبيع بسعر مرتفع للحفاظ على التخصيص الأصلي.', en: 'Bot rebalances at fixed intervals, buying low and selling high to maintain the original allocation.' },
  proportionalModeDesc: { ar: 'يُفعّل إعادة التوازن عندما تتجاوز حصة الرمز التخصيص المحدد. النسب المئوية الأصغر تعني إعادة توازن أكثر تواتراً.', en: 'Triggers rebalance when a token\'s share exceeds the set allocation. Smaller percentages mean more frequent rebalancing.' },
};

export function tr(key: string, lang: Lang): string {
  return t[key]?.[lang] ?? key;
}
