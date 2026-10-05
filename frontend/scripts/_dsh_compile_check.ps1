#!/usr/bin/env pwsh
# Compile-check every changed module through the running Vite dev server.
$base = 'http://127.0.0.1:5173'
$modules = @(
  '/src/i18n/messages.js',
  '/src/i18n/index.js',
  '/src/App.vue',
  '/src/router/index.js',
  '/src/components/ReportDialog.vue',
  '/src/components/LegalDoc.vue',
  '/src/components/LikersDialog.vue',
  '/src/components/PestEditDialog.vue',
  '/src/components/MessageEntry.vue',
  '/src/components/OfflineIndicator.vue',
  '/src/utils/offlineQueue.js',
  '/src/views/HomeView.vue',
  '/src/views/AboutView.vue',
  '/src/views/PrivacyView.vue',
  '/src/views/TermsView.vue',
  '/src/views/FeedbackCenterView.vue',
  '/src/views/AdminFeedbackView.vue',
  '/src/views/HelpView.vue',
  '/src/views/NewsView.vue',
  '/src/views/NewsDetailView.vue',
  '/src/views/NewsManagementView.vue',
  '/src/views/DetectView.vue',
  '/src/views/EditPostView.vue',
  '/src/views/PostDetailView.vue',
  '/src/views/UserProfileView.vue',
  '/src/views/ConsultView.vue',
  '/src/views/NotificationsView.vue',
  '/src/views/ContentReviewView.vue',
  '/src/views/ForumBoardView.vue',
  '/src/views/ForumFavoritesView.vue',
  '/src/views/ForumView.vue',
  '/src/views/NewPostView.vue',
  '/src/views/HistoryView.vue',
  '/src/views/AlertsView.vue',
  '/src/views/CalendarView.vue',
  '/src/views/PestEncyclopediaView.vue',
  '/src/views/MessagesView.vue',
  '/src/views/AdminDashboardView.vue'
)

$fail = 0
foreach ($m in $modules) {
  try {
    $r = Invoke-WebRequest "$base$m" -UseBasicParsing -TimeoutSec 90
    Write-Output ("OK   {0,-44} {1} bytes" -f $m, $r.Content.Length)
  } catch {
    $fail++
    Write-Output ("FAIL {0,-44} {1}" -f $m, $_.Exception.Message)
    if ($_.ErrorDetails.Message) { Write-Output ("     " + ($_.ErrorDetails.Message -split "`n" | Select-Object -First 8 -join "`n     ")) }
  }
}
Write-Output ""
Write-Output "failures: $fail / $($modules.Count)"
