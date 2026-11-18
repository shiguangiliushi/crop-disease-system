<template>
  <div class="news-management tinted-page">
    <!-- 第 117 批：原来的「返回」按钮已移除（本页现在在管理后台外壳里，左侧栏就是导航） -->

    <!-- 页头（第 29 批：改用全局 .admin-hero 的深绿实底样式，
         原来浅绿页头铺在浅绿工作区底上会糊成一片） -->
    <div class="admin-hero">
      <div class="admin-hero-main">
        <span class="admin-hero-icon"><i class="bi bi-newspaper"></i></span>
        <div>
          <h2>{{ t('newsMgmt.title') }}</h2>
          <p>{{ t('newsMgmt.subtitle') }}</p>
        </div>
      </div>
      <div class="admin-hero-actions">
        <!-- 第 88 批修复：这里原来写了 `type="primary"`，而全局 theme.css（在
             Element Plus 之后引入）有一条
             `.el-button--primary:not(.is-link):not(.is-text):not(.is-plain):not(.is-disabled)`
             把背景设成 --gradient-brand。它与 `.btn-on-brand.el-button` 争这个按钮时，
             本按钮的底色被涂成**深绿渐变**，而文字色是 .btn-on-brand 给的**深绿**
             （--brand-700）—— 深绿字压深绿底，就是"文字看不清"。
             背景走 `background:` 简写、文字走 CSS 变量，两边各赢一半，才出现这种半吊子状态。
             修法与新闻详情页返回按钮（第 81 批）一致：**去掉 type="primary"**，
             那条全局规则就不再命中；`.btn-on-brand` 本身就提供白底 + 深绿字。
             ↓ 不要把它改回 type="primary"（理由同第 81 批，改了就是深绿底 + 深绿字）。 -->
        <el-button size="large" class="add-btn btn-on-brand" @click="handleCreate">
          <el-icon><Plus /></el-icon>
          <span>{{ t('newsMgmt.newNews') }}</span>
        </el-button>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-input
        v-model="filters.keyword"
        class="filter-keyword"
        :placeholder="t('newsMgmt.searchPlaceholder')"
        clearable
        @keyup.enter="handleSearch"
        @clear="handleSearch"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>

      <!-- 第 88 批：清空下拉也要重查（el-select 的清除不发 change，只发 clear） -->
      <el-select v-model="filters.category" class="filter-select" :placeholder="t('newsMgmt.allCategories')" clearable @change="handleSearch" @clear="handleSearch">
        <el-option v-for="item in NEWS_CATEGORIES" :key="item.value" :label="t(item.labelKey)" :value="item.value" />
      </el-select>

      <el-select v-model="filters.status" class="filter-select" :placeholder="t('newsMgmt.allStatus')" clearable @change="handleSearch" @clear="handleSearch">
        <el-option :label="t('newsMgmt.tabPublished')" value="published" />
        <el-option :label="t('newsMgmt.draft')" value="draft" />
      </el-select>

      <el-button type="primary" plain @click="handleSearch">{{ t('newsMgmt.query') }}</el-button>
      <el-button text @click="resetFilters">{{ t('newsMgmt.reset') }}</el-button>

      <span class="filter-total">{{ t('newsMgmt.totalCount', { count: pagination.total }) }}</span>
    </div>

    <!-- 第 403 批：数据看板（统计行 + 趋势/分类/Top/标签云）。
         放在筛选栏之后、新闻列表之前：管理员先看整体走势，再往下处理具体条目。
         接口未就绪/请求失败时各区块显示空态，绝不影响下方列表与统计卡。 -->
    <section class="news-dashboard" :aria-label="t('newsMgmt.dashboardTitle')">
      <div class="dashboard-head">
        <div class="dashboard-head-text">
          <h3>{{ t('newsMgmt.dashboardTitle') }}</h3>
          <p>{{ t('newsMgmt.dashboardSubtitle') }}</p>
        </div>
        <div class="dashboard-range">
          <span class="dashboard-range-label">{{ t('newsMgmt.rangeLabel') }}</span>
          <el-radio-group v-model="statsDays" size="small" @change="loadNewsStats">
            <el-radio-button :value="7">{{ t('newsMgmt.range7d') }}</el-radio-button>
            <el-radio-button :value="30">{{ t('newsMgmt.range30d') }}</el-radio-button>
            <el-radio-button :value="90">{{ t('newsMgmt.range90d') }}</el-radio-button>
          </el-radio-group>
        </div>
      </div>

      <!-- 统计行：总数 / 已发布 / 草稿 / 精选 / 定时 / 总阅读量 -->
      <div class="admin-stats dashboard-stats">
        <div
          v-for="card in statCards"
          :key="card.key"
          class="stat-tile"
          :class="card.tone"
        >
          <span class="stat-tile-icon"><i :class="card.icon"></i></span>
          <div>
            <div class="stat-tile-value">{{ formatNumber(card.value) }}</div>
            <div class="stat-tile-label">{{ card.label }}</div>
          </div>
        </div>
      </div>

      <!-- 首次加载：骨架；接口失败后 show 空态（statsLoaded） -->
      <el-skeleton v-if="statsLoading && !statsLoaded" :rows="6" animated class="dashboard-skeleton" />

      <template v-else>
        <div class="dashboard-grid">
          <section class="panel-card">
            <div class="panel-head">
              <span class="panel-icon"><i class="fas fa-chart-line"></i></span>
              <h4 class="panel-title">{{ t('newsMgmt.chartPublishTrend') }}</h4>
              <span class="panel-count">{{ t('newsMgmt.rangeDays', { days: statsDays }) }}</span>
            </div>
            <div class="panel-body dashboard-chart-body">
              <Line v-if="!publishTrendEmpty" :data="publishTrendChart" :options="trendOptions" />
              <div v-else class="dashboard-empty">
                <i class="fas fa-chart-line"></i>
                <span>{{ t('newsMgmt.chartEmpty') }}</span>
              </div>
            </div>
          </section>

          <section class="panel-card">
            <div class="panel-head">
              <span class="panel-icon"><i class="fas fa-chart-pie"></i></span>
              <h4 class="panel-title">{{ t('newsMgmt.chartCategory') }}</h4>
            </div>
            <div class="panel-body dashboard-chart-body">
              <Doughnut v-if="!categoryEmpty" :data="categoryChart" :options="categoryOptions" />
              <div v-else class="dashboard-empty">
                <i class="fas fa-chart-pie"></i>
                <span>{{ t('newsMgmt.chartEmpty') }}</span>
              </div>
            </div>
          </section>
        </div>

        <div class="dashboard-grid">
          <section class="panel-card">
            <div class="panel-head">
              <span class="panel-icon"><i class="fas fa-fire"></i></span>
              <h4 class="panel-title">{{ t('newsMgmt.chartTopViewed') }}</h4>
              <span class="panel-count">{{ t('newsMgmt.totalCount', { count: topViewedNews.length }) }}</span>
            </div>
            <div class="panel-body dashboard-list-body">
              <ol v-if="topViewedNews.length" class="top-viewed-list">
                <li v-for="(item, index) in topViewedNews" :key="item.id">
                  <button type="button" class="top-viewed-item" @click="goToNewsDetail(item.id)">
                    <span class="top-viewed-rank" :class="`is-${index + 1}`">{{ index + 1 }}</span>
                    <span class="top-viewed-title">{{ localizedField(item, 'title') }}</span>
                    <span class="top-viewed-views">
                      <i class="fas fa-eye"></i> {{ t('newsMgmt.viewsUnit', { count: formatNumber(item.views) }) }}
                    </span>
                  </button>
                </li>
              </ol>
              <div v-else class="dashboard-empty dashboard-empty--compact">
                <i class="fas fa-fire"></i>
                <span>{{ t('newsMgmt.chartEmpty') }}</span>
              </div>
            </div>
          </section>

          <section class="panel-card">
            <div class="panel-head">
              <span class="panel-icon"><i class="fas fa-tags"></i></span>
              <h4 class="panel-title">{{ t('newsMgmt.chartTagCloud') }}</h4>
              <span class="panel-count">{{ t('newsMgmt.totalCount', { count: tagCloudItems.length }) }}</span>
            </div>
            <div class="panel-body dashboard-tag-body">
              <div v-if="tagCloudItems.length" class="tag-cloud">
                <span
                  v-for="tag in tagCloudItems"
                  :key="tag.name"
                  class="tag-cloud-item"
                  :style="tag.style"
                >
                  {{ tag.name }}<em>{{ tag.count }}</em>
                </span>
              </div>
              <div v-else class="dashboard-empty dashboard-empty--compact">
                <i class="fas fa-tags"></i>
                <span>{{ t('newsMgmt.chartEmpty') }}</span>
              </div>
            </div>
          </section>
        </div>
      </template>
    </section>

    <!-- 列表（第 29 批：卡片加"着色头条"，表格加斑马纹，整块不再是一张白纸） -->
    <el-card class="table-card admin-list-card" shadow="never">
      <div class="panel-head">
        <span class="panel-icon"><i class="fas fa-table-list"></i></span>
        <h3 class="panel-title">{{ t('newsMgmt.listTitle') }}</h3>
        <span class="panel-count">{{ t('newsMgmt.totalCount', { count: pagination.total }) }}</span>
        <div class="panel-head-right">
          <span class="panel-hint">{{ t('newsMgmt.listHint') }}</span>
        </div>
      </div>

      <div class="panel-body">
        <el-table v-loading="loading" :data="newsList" style="width: 100%" row-key="id">
        <el-table-column :label="t('newsMgmt.colCover')" width="110">
          <template #default="{ row }">
            <div class="cover-cell">
              <img v-if="row.image_url" :src="row.image_url" class="cover-img" :alt="t('newsMgmt.colCover')" />
              <div v-else class="cover-placeholder"><i class="bi bi-image"></i></div>
            </div>
          </template>
        </el-table-column>

        <el-table-column :label="t('newsMgmt.colTitle')" min-width="240">
          <template #default="{ row }">
            <div class="title-cell">
              <!-- 第 79 批：标题与来源是内容数据（后端已有 title_en / source_en），
                   原来直接渲染中文，英文界面下后台新闻列表整列是中文 -->
              <span class="title-text">{{ localizedField(row, 'title') }}</span>
              <div class="title-meta">
                <el-tag size="small" effect="plain" type="success">{{ getNewsCategoryLabel(row.category, t) }}</el-tag>
                <!-- 第 399 批：管理员一眼能认出头条条目（读者端头条区只会取前 3 条） -->
                <el-tag v-if="row.is_featured" size="small" effect="light" type="warning">
                  <i class="fas fa-star"></i> {{ t('news.featuredBadge') }}
                </el-tag>
                <span v-if="row.source" class="source-text">
                  {{ t('newsMgmt.sourceLabel', { source: localizedField(row, 'source') }) }}
                </span>
                <!-- 第 401 批：原文外链小图标（新标签页打开，不影响表格行本身） -->
                <a
                  v-if="row.external_url"
                  class="title-ext-link"
                  :href="row.external_url"
                  target="_blank"
                  rel="noopener noreferrer"
                  :title="t('news.externalLink')"
                  :aria-label="t('news.externalLink')"
                >
                  <i class="fas fa-arrow-up-right-from-square"></i>
                </a>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column :label="t('newsMgmt.colAuthor')" width="110">
          <template #default="{ row }">{{ row.author_name || t('newsMgmt.systemAdmin') }}</template>
        </el-table-column>

        <el-table-column :label="t('newsMgmt.colPublishedAt')" width="170">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>

        <el-table-column :label="t('newsMgmt.colStatus')" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_published ? 'success' : 'info'" effect="light">
              {{ row.is_published ? t('newsMgmt.tabPublished') : t('newsMgmt.draft') }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column :label="t('newsMgmt.colActions')" width="230" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="handleEdit(row)">{{ t('news.edit') }}</el-button>
            <el-button size="small" :type="row.is_published ? 'warning' : 'success'" link @click="togglePublishStatus(row)">
              {{ row.is_published ? t('newsMgmt.unpublish') : t('newsMgmt.publishLabel') }}
            </el-button>
            <el-popconfirm :title="t('newsMgmt.deleteConfirm')" :confirm-button-text="t('news.delete')" :cancel-button-text="t('common.cancel')" @confirm="handleDelete(row.id)">
              <template #reference>
                <el-button size="small" type="danger" link>{{ t('news.delete') }}</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>

        <template #empty>
          <div class="table-empty">
            <i class="bi bi-inbox"></i>
            <p>{{ t('newsMgmt.empty') }}</p>
          </div>
        </template>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="pagination.currentPage"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="pagination.total"
          background
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
      </div>
    </el-card>

    <!-- 新增 / 编辑（第 33 批：与「行业动态」页的编辑弹窗统一成深绿头条 + 分段表单）
         第 399 批：width 改用 CSS min()（与行业动态页弹窗一致）—— 固定 720px 在
         375px 手机上右侧溢出、弹窗内容被裁掉；min() 让桌面保持 720px、窄屏收成屏宽 - 24px。 -->
    <el-dialog
      v-model="dialogVisible"
      width="min(720px, calc(100vw - 24px))"
      top="5vh"
      :close-on-click-modal="false"
      destroy-on-close
      class="form-dialog"
    >
      <template #header>
        <div class="form-dialog-head">
          <span class="form-dialog-head-icon">
            <i :class="isEditing ? 'fas fa-pen-to-square' : 'fas fa-plus'"></i>
          </span>
          <div>
            <h3>{{ formTitle }}</h3>
            <p>{{ t('newsMgmt.dialogCreateHint') }}</p>
          </div>
        </div>
      </template>

      <div class="form-dialog-body">
        <el-form ref="newsFormRef" :model="form" :rules="rules" label-position="top">
          <!-- 基本信息 -->
          <section class="form-section">
            <div class="form-section-head">
              <i class="fas fa-circle-info"></i>
              <h4>{{ t('news.basicInfo') }}</h4>
              <span class="section-hint">{{ t('newsMgmt.basicInfoHint') }}</span>
            </div>

            <el-form-item prop="title">
              <template #label>
                <span class="form-label-row">
                  <span>{{ t('news.fieldTitle') }}</span>
                  <!-- 第 404 批：AI 优化标题（需要正文；失败不清空已有标题） -->
                  <button
                    v-if="canManage"
                    type="button"
                    class="ai-btn"
                    :disabled="Boolean(aiBusy) || !aiPrerequisite('title')"
                    :title="aiPrerequisite('title') ? t('newsMgmt.aiOptimizeTitle') : aiDisabledHint('title')"
                    @click="runAiAssist('title')"
                  >
                    <i :class="aiBusy === 'title' ? 'fas fa-spinner fa-spin' : 'fas fa-wand-magic-sparkles'"></i>
                    {{ aiBusy === 'title' ? t('newsMgmt.aiBusy') : t('newsMgmt.aiOptimizeTitle') }}
                  </button>
                </span>
              </template>
              <el-input
                v-model="form.title"
                maxlength="200"
                show-word-limit
                :placeholder="t('news.fieldTitlePlaceholder')"
              />
            </el-form-item>

            <!-- 第 404 批：英文标题（英文界面读者直接看这个；可用 AI 翻译一键回填标题+正文） -->
            <el-form-item>
              <template #label>
                <span class="form-label-row">
                  <span>{{ t('newsMgmt.fieldTitleEn') }}</span>
                  <button
                    v-if="canManage"
                    type="button"
                    class="ai-btn"
                    :disabled="Boolean(aiBusy) || !aiPrerequisite('translate')"
                    :title="aiPrerequisite('translate') ? t('newsMgmt.aiTranslate') : aiDisabledHint('translate')"
                    @click="runAiAssist('translate')"
                  >
                    <i :class="aiBusy === 'translate' ? 'fas fa-spinner fa-spin' : 'fas fa-language'"></i>
                    {{ aiBusy === 'translate' ? t('newsMgmt.aiBusy') : t('newsMgmt.aiTranslate') }}
                  </button>
                </span>
              </template>
              <el-input
                v-model="form.title_en"
                maxlength="200"
                show-word-limit
                clearable
                :placeholder="t('newsMgmt.titleEnPlaceholder')"
              />
              <p class="field-hint">
                <i class="fas fa-language"></i>
                {{ t('newsMgmt.titleEnHint') }}
              </p>
            </el-form-item>

            <el-row :gutter="16">
              <el-col :xs="24" :sm="12">
                <el-form-item :label="t('news.fieldCategory')" prop="category">
                  <el-select v-model="form.category" :placeholder="t('news.fieldCategoryPlaceholder')" style="width: 100%">
                    <el-option v-for="item in NEWS_CATEGORIES" :key="item.value" :label="t(item.labelKey)" :value="item.value" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :xs="24" :sm="12">
                <el-form-item :label="t('news.fieldSource')">
                  <el-input v-model="form.source" maxlength="100" :placeholder="t('newsMgmt.sourcePlaceholder')" />
                </el-form-item>
                <!-- 第 404 批：英文来源（可选；英文界面下来源从这里取） -->
                <el-form-item :label="t('newsMgmt.fieldSourceEn')">
                  <el-input v-model="form.source_en" maxlength="100" :placeholder="t('newsMgmt.sourceEnPlaceholder')" />
                </el-form-item>
              </el-col>
            </el-row>

            <el-form-item>
              <template #label>
                <span class="form-label-row">
                  <span>{{ t('news.tagLabel') }}</span>
                  <!-- 第 404 批：AI 建议标签（回填为逗号分隔的标签数组，可再手动增删） -->
                  <button
                    v-if="canManage"
                    type="button"
                    class="ai-btn"
                    :disabled="Boolean(aiBusy) || !aiPrerequisite('tags')"
                    :title="aiPrerequisite('tags') ? t('newsMgmt.aiSuggestTags') : aiDisabledHint('tags')"
                    @click="runAiAssist('tags')"
                  >
                    <i :class="aiBusy === 'tags' ? 'fas fa-spinner fa-spin' : 'fas fa-tags'"></i>
                    {{ aiBusy === 'tags' ? t('newsMgmt.aiBusy') : t('newsMgmt.aiSuggestTags') }}
                  </button>
                </span>
              </template>
              <el-select
                v-model="form.tags"
                multiple
                filterable
                allow-create
                default-first-option
                :reserve-keyword="false"
                :placeholder="t('newsMgmt.tagMultiPlaceholder')"
                style="width: 100%"
              />
              <p class="field-hint">{{ t('newsMgmt.tagHint') }}</p>
            </el-form-item>

            <!-- 第 401 批：原文链接 / 关联病害（与行业动态页弹窗同口径） -->
            <el-form-item :label="t('field.externalUrl')">
              <el-input
                v-model="form.external_url"
                type="url"
                maxlength="500"
                show-word-limit
                clearable
                :placeholder="t('news.externalUrlPlaceholder')"
              />
              <p class="field-hint">
                <i class="fas fa-arrow-up-right-from-square"></i>
                {{ t('news.externalUrlHint') }}
              </p>
            </el-form-item>

            <el-form-item :label="t('field.relatedPests')">
              <el-select
                v-model="form.related_pests"
                multiple
                filterable
                clearable
                :placeholder="t('news.relatedPestsPlaceholder')"
                style="width: 100%"
              >
                <el-option
                  v-for="pest in pestOptions"
                  :key="pest.id"
                  :label="`${localizedField(pest, 'crop_type')} - ${localizedField(pest, 'name')}`"
                  :value="pest.id"
                />
              </el-select>
              <p class="field-hint">
                <i class="fas fa-leaf"></i>
                {{ t('news.relatedPestsHint') }}
              </p>
            </el-form-item>
          </section>

          <!-- 正文 -->
          <section class="form-section">
            <div class="form-section-head">
              <i class="fas fa-align-left"></i>
              <h4>{{ t('news.bodySection') }}</h4>
              <span class="section-hint">{{ t('newsMgmt.bodyHint') }}</span>
            </div>

            <el-form-item :label="t('news.searchByContent')" prop="content">
              <div class="editor-wrap">
                <RichTextEditor v-model="form.content" />
              </div>
            </el-form-item>

            <!-- 第 404 批：英文正文（纯文本/HTML 均可，写入 content_en；留空时英文界面回落中文） -->
            <el-form-item>
              <template #label>
                <span class="form-label-row">
                  <span>{{ t('newsMgmt.fieldContentEn') }}</span>
                </span>
              </template>
              <el-input
                v-model="form.content_en"
                type="textarea"
                :rows="4"
                resize="none"
                :placeholder="t('newsMgmt.contentEnPlaceholder')"
              />
              <p class="field-hint">
                <i class="fas fa-language"></i>
                {{ t('newsMgmt.contentEnHint') }}
              </p>
            </el-form-item>

            <!-- 第 399 批 · P0-3：列表摘要。留空时读者端回退正文截断；限 200 字与后端一致 -->
            <el-form-item>
              <template #label>
                <span class="form-label-row">
                  <span>{{ t('news.fieldSummary') }}</span>
                  <!-- 第 404 批：AI 生成摘要（需要正文；失败不清空手写摘要） -->
                  <button
                    v-if="canManage"
                    type="button"
                    class="ai-btn"
                    :disabled="Boolean(aiBusy) || !aiPrerequisite('summary')"
                    :title="aiPrerequisite('summary') ? t('newsMgmt.aiGenerateSummary') : aiDisabledHint('summary')"
                    @click="runAiAssist('summary')"
                  >
                    <i :class="aiBusy === 'summary' ? 'fas fa-spinner fa-spin' : 'fas fa-wand-magic-sparkles'"></i>
                    {{ aiBusy === 'summary' ? t('newsMgmt.aiBusy') : t('newsMgmt.aiGenerateSummary') }}
                  </button>
                </span>
              </template>
              <el-input
                v-model="form.summary"
                type="textarea"
                :rows="2"
                resize="none"
                maxlength="200"
                show-word-limit
                :placeholder="t('news.fieldSummaryPlaceholder')"
              />
            </el-form-item>
          </section>

          <!-- 封面与状态 -->
          <section class="form-section">
            <div class="form-section-head">
              <i class="fas fa-image"></i>
              <h4>{{ t('newsMgmt.coverPublish') }}</h4>
              <span class="section-hint">{{ t('news.coverHint') }}</span>
            </div>

            <el-form-item :label="t('newsMgmt.coverLabel')">
              <div class="cover-field">
                <el-upload
                  class="cover-uploader"
                  :auto-upload="false"
                  :show-file-list="false"
                  accept="image/*"
                  :on-change="handleImageChange"
                >
                  <div class="upload-tile cover-tile">
                    <img v-if="coverPreview" :src="coverPreview" :alt="t('newsMgmt.coverPreview')" />
                    <div v-else class="upload-tile-empty">
                      <i class="fas fa-cloud-arrow-up"></i>
                      <span>{{ t('newsMgmt.uploadCover') }}</span>
                      <small>{{ t('newsMgmt.coverFormatHint') }}</small>
                    </div>
                    <div v-if="coverPreview" class="upload-tile-actions">
                      <button type="button" :title="t('newsMgmt.changeCover')">
                        <i class="fas fa-rotate"></i>
                      </button>
                      <button type="button" :title="t('newsMgmt.removeCover')" @click.stop="removeCover">
                        <i class="fas fa-trash"></i>
                      </button>
                    </div>
                  </div>
                </el-upload>
              </div>
            </el-form-item>

            <el-form-item :label="t('news.publishStatus')">
              <el-radio-group v-model="form.is_published">
                <el-radio-button :value="true">{{ t('newsMgmt.publishLabel') }}</el-radio-button>
                <el-radio-button :value="false">{{ t('newsMgmt.saveDraft') }}</el-radio-button>
              </el-radio-group>
              <p class="field-hint">
                <i class="fas fa-circle-info"></i>
                {{ t('newsMgmt.draftHint') }}
              </p>
            </el-form-item>

            <!-- 第 399 批 · P0-1：设为精选后读者端列表顶部头条区优先展示（至多 3 条） -->
            <el-form-item :label="t('field.featured')">
              <el-switch v-model="form.is_featured" />
              <p class="field-hint">
                <i class="fas fa-star"></i>
                {{ t('news.featuredHint') }}
              </p>
            </el-form-item>

            <!-- 第 38 批：定时发布 -->
            <el-form-item :label="t('newsMgmt.scheduledPublish')">
              <el-date-picker
                v-model="form.published_at"
                type="datetime"
                :placeholder="t('newsMgmt.scheduledHint')"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DDTHH:mm:ssZ"
                clearable
                style="width: 100%"
              />
              <p class="field-hint">
                <i class="fas fa-clock"></i>
                {{ t('newsMgmt.scheduledNote') }}
              </p>
            </el-form-item>
          </section>
        </el-form>
      </div>

      <template #footer>
        <div class="form-dialog-footer">
          <span class="footer-hint">
            <i class="fas fa-shield-halved"></i> {{ t('news.saveNow') }}
          </span>
          <span>
            <el-button @click="dialogVisible = false">{{ t('common.cancel') }}</el-button>
            <el-button type="primary" :loading="submitting" @click="submitForm">
              <i class="fas fa-check"></i> {{ t('profile.save') }}
            </el-button>
          </span>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
// 新闻管理（管理端）
// 路由：/admin/news —— 发布/编辑/删除都在本页内完成，不额外开路由。
// 面向读者的详情是另一个组件 NewsDetailView（/news/:id）。
//
// 页面由三块组成：
//   1) 统计卡（总数 / 已发布 / 草稿）—— 用 page_size=1 只取 count，见 fetchStats
//   2) 筛选栏（关键词 / 状态 / 分类）+ 新建按钮
//   3) 列表表格：编辑、切换发布状态、删除
//
// 改这个文件前值得知道的几件事：
//   · **模板顶部有一段"不要把它改回 type=primary"的说明（第 88 批）**，
//     那是按钮文字看不清踩过的坑，别绕过；
//   · 正文校验是"先用正则剥掉 HTML 标签、再数剩余长度"，因为存的是富文本 ——
//     直接数原文长度会让"只插了一张图"的空新闻通过校验；
//   · 封面 5MB 上限在后端、本页、移动端各写了一份（i18n key 名字里也带数字），
//     改动时要一起看。
import { computed, onMounted, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { Plus, Search } from '@element-plus/icons-vue';
import { format } from 'date-fns';
// 第 403 批：数据看板图表（本页只注册用到的 controller/element，方式与 AdminDashboardView 一致）
import { Doughnut, Line } from 'vue-chartjs';
import {
  ArcElement,
  CategoryScale,
  Chart as ChartJS,
  DoughnutController,
  Filler,
  Legend,
  LineController,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
} from 'chart.js';
import RichTextEditor from '@/components/RichTextEditor.vue';
import {
  NEWS_CATEGORIES,
  aiAssistNews,
  createNews,
  deleteNews,
  fetchNewsDetail,
  fetchNewsList,
  fetchNewsStats,
  formatNewsError,
  getNewsCategoryLabel,
  toggleNewsPublished,
  updateNews,
} from '@/api/news';
import { toAbsoluteMediaUrl } from '@/api/http';
// 第 401 批：关联病害多选的选项来自病害百科列表
import { fetchPestList } from '@/api/pest';
import { useRoute, useRouter } from 'vue-router';  // 第 121 批：旧深链重定向进来的 ?action=
import { useAuthStore } from '@/stores/auth';  // 第 404 批：AI 辅助仅内容维护者可见
import { useI18n } from '@/i18n';  // 第 66 批：多语言
import { useLocalized } from '@/utils/localized';  // 第 79 批：新闻标题/来源等内容数据
// 第 117 批：去掉 BackButton（本页已挪进管理后台外壳，侧栏就是导航）

// 第 403 批：按需注册（register 是幂等的，各页面注册自己用到的图表类型即可，不要在 main.js 全局注册）
ChartJS.register(
  LineController, LineElement, PointElement, CategoryScale, LinearScale,
  Filler, Legend, Tooltip, DoughnutController, ArcElement,
);

const BRAND = '#3d9a68';
const BRAND_SOFT = 'rgba(61, 154, 104, 0.16)';
// 分类环形图配色：品牌绿系 + 两个辅助色，和 AdminDashboardView 的调色板保持一致
const CHART_PALETTE = ['#3d9a68', '#5fb088', '#93cdad', '#2a7f53', '#d9922f', '#3d7ea6', '#cf4436', '#9dada5'];

const { t } = useI18n();
const { localizedField } = useLocalized();

/**
 * 第 404 批：AI 辅助按钮的可见性
 * 本页路由本身已要求 CONTENT 能力 + news 内容模块（见 router meta），这里再按能力
 * 确认一次：AI 是对内容的增强操作，只让内容维护者看到入口，不另造一套权限判断。
 */
const authStore = useAuthStore();
const canManage = computed(() => authStore.isAdmin || authStore.hasContentModule('news'));

/**
 * 第 401 批：关联病害下拉的选项（按需加载一次）
 * ------------------------------------------------------------------
 * 病害词条全量最多 100 条，够本页使用；接口失败时保持空列表、不打扰管理员 ——
 * 关联病害只是新闻的增强信息，不能让它阻断"保存新闻"这条主流程。
 */
const pestOptions = ref([]);
const pestOptionsLoaded = ref(false);
const ensurePestOptions = async () => {
  if (pestOptionsLoaded.value) return;
  pestOptionsLoaded.value = true;
  try {
    const data = await fetchPestList({ page_size: 100 });
    const results = Array.isArray(data?.results) ? data.results : Array.isArray(data) ? data : [];
    pestOptions.value = results.filter((item) => item && item.id !== undefined && item.id !== null);
  } catch (error) {
    console.warn('获取病害选项失败（关联病害下拉留空）:', error);
    pestOptions.value = [];
  }
};

/** 病害 id 归一化成数字数组（后端主键是整数，字符串 id 会让 el-select 回显不上） */
const toPestIdArray = (value) => {
  if (!Array.isArray(value)) return [];
  return value
    .map((id) => (typeof id === 'number' ? id : Number(id)))
    .filter((id) => Number.isFinite(id) && id > 0);
};

/** 第 401 批：响应里有没有 related_pests 字段 —— 没有就不提交 clear_related_pests，避免误清空 */
const relatedPestsKnown = ref(true);

// ---------- 列表 ----------
const loading = ref(false);
const newsList = ref([]);

const filters = reactive({
  keyword: '',
  category: '',
  status: '',
});

const pagination = reactive({
  currentPage: 1,
  pageSize: 10,
  total: 0,
});

// 统计小卡数据（第 28 批）
const stats = ref({ total: 0, published: 0, draft: 0 });

/**
 * 拉取统计数字：各用一次 page_size=1 的请求拿 count，
 * 失败不打扰用户（统计只是辅助信息）。
 */
const fetchStats = async () => {
  try {
    const [all, published, draft] = await Promise.all([
      fetchNewsList({ page: 1, page_size: 1 }),
      fetchNewsList({ page: 1, page_size: 1, is_published: 'true' }),
      fetchNewsList({ page: 1, page_size: 1, is_published: 'false' }),
    ]);
    stats.value = {
      total: all.count || 0,
      published: published.count || 0,
      draft: draft.count || 0,
    };
  } catch (error) {
    console.warn('获取新闻统计失败:', error);
  }
};

// ---------- 第 403 批：新闻数据看板 ----------
const statsDays = ref(30);
const newsStats = ref(null);
const statsLoading = ref(true);   // 首次渲染即显示骨架，避免「先空态、后数据」闪一下
const statsLoaded = ref(false);
let statsRequestSeq = 0;

/** 数字千分位；未加载的统计项显示「—」，避免误报 0 */
const formatNumber = (value) => {
  if (value === null || value === undefined || value === '') return '—';
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString() : String(value);
};

/** YYYY-MM-DD → MM-DD（图表横轴用；不用 new Date，避免时区把日期挪一天） */
const formatMonthDay = (value) => {
  const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})/);
  return match ? `${match[2]}-${match[3]}` : String(value || '');
};

/**
 * 看板统计行（6 张卡）
 * 数据看板接口未就绪时，前 3 项回落到第 28 批的列表 count（fetchStats），
 * 精选 / 定时 / 总阅读量显示「—」—— 不能凭空显示 0 误导管理员。
 */
const statCards = computed(() => {
  const totals = newsStats.value?.totals && typeof newsStats.value.totals === 'object'
    ? newsStats.value.totals
    : null;
  return [
    { key: 'all', icon: 'fas fa-newspaper', value: totals ? totals.all : stats.value.total, label: t('newsMgmt.tabAll'), tone: '' },
    { key: 'published', icon: 'fas fa-circle-check', value: totals ? totals.published : stats.value.published, label: t('newsMgmt.tabPublished'), tone: 'stat-tile--ok' },
    { key: 'draft', icon: 'fas fa-file-pen', value: totals ? totals.draft : stats.value.draft, label: t('newsMgmt.draft'), tone: 'stat-tile--pending' },
    { key: 'featured', icon: 'fas fa-star', value: totals ? (totals.featured ?? 0) : null, label: t('newsMgmt.statFeatured'), tone: 'stat-tile--processing' },
    { key: 'scheduled', icon: 'fas fa-clock', value: totals ? (totals.scheduled ?? 0) : null, label: t('newsMgmt.statScheduled'), tone: '' },
    { key: 'views', icon: 'fas fa-eye', value: totals ? (totals.views_total ?? 0) : null, label: t('newsMgmt.statViews'), tone: '' },
  ];
});

// ---- 发布量趋势（折线） ----
const publishTrendRows = computed(() => (Array.isArray(newsStats.value?.publish_trend) ? newsStats.value.publish_trend : []));
const publishTrendEmpty = computed(() => {
  if (publishTrendRows.value.length === 0) return true;
  return publishTrendRows.value.every((row) => !Number(row?.count));
});
const publishTrendChart = computed(() => ({
  labels: publishTrendRows.value.map((row) => row?.date || ''),
  datasets: [{
    label: t('newsMgmt.chartPublishTrend'),
    data: publishTrendRows.value.map((row) => Number(row?.count) || 0),
    borderColor: BRAND,
    backgroundColor: BRAND_SOFT,
    fill: true,
    tension: 0.32,
    borderWidth: 2,
    pointRadius: 2,
    pointHoverRadius: 4,
  }],
}));
const trendOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  scales: {
    x: {
      grid: { display: false },
      ticks: {
        color: '#78897f',
        font: { size: 11 },
        maxRotation: 0,
        autoSkipPadding: 8,
        // 后端给 YYYY-MM-DD，横轴只显示 MM-DD（标签过长会在窄屏挤成一团）
        callback(value) {
          return formatMonthDay(this.getLabelForValue(value));
        },
      },
    },
    y: {
      beginAtZero: true,
      grid: { color: '#eef5f1' },
      ticks: { color: '#78897f', precision: 0, font: { size: 11 } },
    },
  },
};

// ---- 分类占比（环形；标签走 i18n，不用后端中文 label） ----
const categoryRows = computed(() => (Array.isArray(newsStats.value?.category_distribution) ? newsStats.value.category_distribution : []));
const categoryEmpty = computed(() => {
  if (categoryRows.value.length === 0) return true;
  return categoryRows.value.every((row) => !Number(row?.count));
});
const categoryChart = computed(() => ({
  labels: categoryRows.value.map((row) => getNewsCategoryLabel(row?.category, t)),
  datasets: [{
    data: categoryRows.value.map((row) => Number(row?.count) || 0),
    backgroundColor: CHART_PALETTE,
    borderWidth: 0,
  }],
}));
const categoryOptions = {
  responsive: true,
  maintainAspectRatio: false,
  cutout: '58%',
  plugins: {
    legend: { position: 'bottom', labels: { boxWidth: 10, color: '#566b60', font: { size: 11 } } },
  },
};

// ---- 阅读量 Top（最多 10 条） ----
const topViewedNews = computed(() => {
  const rows = Array.isArray(newsStats.value?.top_viewed) ? newsStats.value.top_viewed : [];
  return rows.slice(0, 10);
});

/**
 * 标签云：按出现次数决定字号与深浅（12→20px、0.62→1）。
 * 纯展示；最多 20 个，防止标签特别多时把卡片撑高/撑破。
 */
const tagCloudItems = computed(() => {
  const rows = Array.isArray(newsStats.value?.tag_cloud) ? newsStats.value.tag_cloud : [];
  const maxCount = rows.reduce((top, row) => Math.max(top, Number(row?.count) || 0), 0);
  return rows
    .filter((row) => row && row.name)
    .slice(0, 20)
    .map((row) => {
      const count = Number(row.count) || 0;
      const ratio = maxCount > 0 ? count / maxCount : 0;
      return {
        name: row.name,
        count,
        style: {
          fontSize: `${12 + Math.round(ratio * 8)}px`,
          opacity: String(0.62 + ratio * 0.38),
        },
      };
    });
});

/**
 * 拉取看板聚合数据
 * - 失败静默：只 console.warn，保留已有数据/空态，不弹错误打断管理员；
 * - 序号防竞态：快速切 7/30/90 时，旧响应不能覆盖新范围；
 * - 与新闻列表、统计卡完全解耦：这里失败不影响下方表格。
 */
const loadNewsStats = async () => {
  const requestId = ++statsRequestSeq;
  statsLoading.value = true;
  try {
    const data = await fetchNewsStats({ days: statsDays.value });
    if (requestId !== statsRequestSeq) return;
    newsStats.value = data;
    statsLoaded.value = true;
  } catch (error) {
    if (requestId !== statsRequestSeq) return;
    console.warn('加载新闻数据看板失败（按空态处理，不影响列表）:', error);
    // 标记已加载：首次失败展示各区块空态；切换范围失败则保留上一份数据
    statsLoaded.value = true;
  } finally {
    if (requestId === statsRequestSeq) statsLoading.value = false;
  }
};

const buildParams = () => {
  const params = {
    page: pagination.currentPage,
    page_size: pagination.pageSize,
  };
  if (filters.keyword) {
    params.search = filters.keyword;
    params.search_type = 'all';
  }
  if (filters.category) params.category = filters.category;
  if (filters.status) params.is_published = filters.status === 'published' ? 'true' : 'false';
  return params;
};

const fetchData = async () => {
  loading.value = true;
  try {
    const data = await fetchNewsList(buildParams());
    newsList.value = data.results;
    pagination.total = data.count;
    fetchStats();
  } catch (error) {
    console.error('获取新闻列表失败:', error);
    newsList.value = [];
    pagination.total = 0;
    ElMessage.error(formatNewsError(error, t('newsMgmt.loadFailed')));
  } finally {
    loading.value = false;
  }
};

const handleSearch = () => {
  pagination.currentPage = 1;
  fetchData();
};

const resetFilters = () => {
  filters.keyword = '';
  filters.category = '';
  filters.status = '';
  handleSearch();
};

const handleSizeChange = (size) => {
  pagination.pageSize = size;
  pagination.currentPage = 1;
  fetchData();
};

const handleCurrentChange = (page) => {
  pagination.currentPage = page;
  fetchData();
};

// ---------- 表单 ----------
const dialogVisible = ref(false);
const submitting = ref(false);
const formTitle = ref(t('newsMgmt.newNews'));
// 第 33 批：弹窗头条要区分"新增/编辑"，用 form.id 判断即可
const isEditing = computed(() => Boolean(form.id));
const newsFormRef = ref(null);

const form = reactive({
  id: null,
  title: '',
  // 第 404 批：英文标题 / 英文正文（来源英文可选）—— 英文界面读者直接看这些字段
  title_en: '',
  content: '',
  content_en: '',
  category: 'notice',
  source: '',
  source_en: '',
  tags: [],
  is_published: true,
  published_at: null,  // 第 38 批：定时发布（留空 = 立即发布）
  // 第 399 批：摘要 / 精选。published_at 本来就在 payload 里，buildNewsFormData
  // 补上对应 append 后，定时发布（含清空）才真正生效。
  summary: '',
  is_featured: false,
  // 第 401 批：原文链接 / 关联病害（关联 id 数组，多选控件直接绑定）
  external_url: '',
  related_pests: [],
});

// ---------- 第 404 批：AI 辅助（标题优化 / 摘要 / 标签 / 翻译成英文） ----------
// 同一时刻只允许一个 AI 请求（aiBusy 记录当前 action），避免并发回填互相覆盖。
const aiBusy = ref('');

/** 正文去掉 HTML 标签后是否有实际文字（RichTextEditor 的空正文可能是 `<p><br></p>`） */
const hasAiContent = computed(() => String(form.content || '').replace(/<[^>]*>/g, '').trim().length > 0);
const hasAiTitle = computed(() => String(form.title || '').trim().length > 0);

/** 每个 AI 动作的前置条件：翻译需要中英两边都有源（标题+正文），其余只需要正文 */
const aiPrerequisite = (action) => (
  action === 'translate' ? hasAiContent.value && hasAiTitle.value : hasAiContent.value
);

/** 按钮禁用时的 title 提示：缺什么说什么，不能一句笼统的"不可用" */
const aiDisabledHint = (action) => (
  action === 'translate' && !hasAiTitle.value ? t('newsMgmt.aiNoTitle') : t('newsMgmt.aiNoContent')
);

/** 按 action 组装请求体（只带后端认识的字段） */
const buildAiPayload = (action) => {
  const title = String(form.title || '').trim();
  if (action === 'tags') {
    return { action, title, summary: String(form.summary || '').trim(), content: form.content || '' };
  }
  return { action, title, content: form.content || '' };
};

/**
 * 执行一次 AI 辅助并把结果回填到表单
 * - 失败只提示、**绝不改表单已有内容**（用户手写的内容比 AI 结果重要）；
 * - 503 → 「AI 暂不可用」；429 → 「操作太频繁」；其它 → 后端 error 或通用失败文案；
 * - 失败不阻断保存：这里不碰 submitting / 表单校验状态。
 */
const runAiAssist = async (action) => {
  if (aiBusy.value || !aiPrerequisite(action) || !canManage.value) return;
  aiBusy.value = action;
  try {
    const data = await aiAssistNews(buildAiPayload(action));

    if (action === 'translate') {
      if (!data || (data.title_en === undefined && data.content_en === undefined)) {
        throw new Error('AI 未返回译文');
      }
      if (data.title_en !== undefined && data.title_en !== null) {
        form.title_en = String(data.title_en);
      }
      if (data.content_en !== undefined && data.content_en !== null) {
        form.content_en = String(data.content_en);
      }
    } else {
      const text = String(data?.text ?? '').trim();
      if (!text) throw new Error('AI 未返回内容');
      if (action === 'title') {
        form.title = text;
      } else if (action === 'summary') {
        form.summary = text;
      } else if (action === 'tags') {
        // 后端返回逗号分隔的标签串；中英文逗号/顿号/分号都拆开，最多 10 个
        form.tags = text
          .split(/[,，、;；]/)
          .map((item) => item.trim())
          .filter(Boolean)
          .slice(0, 10);
      }
    }

    ElMessage.success(t('newsMgmt.aiDone'));
  } catch (error) {
    const status = error?.response?.status;
    // 503（未启用/上游失败）与 429（限流）是**预期内**的运营状态，记 warn 即可；
    // 其它异常才值得 error 级别（便于区分"AI 没开"与"前端写错"）。
    if (status === 503 || status === 429) {
      console.warn('AI 辅助暂不可用/限流:', error?.message || error);
    } else {
      console.error('AI 辅助失败:', error);
    }
    const backendError = error?.response?.data?.error || error?.response?.data?.detail;
    if (status === 503) {
      ElMessage.warning(t('newsMgmt.aiUnavailable'));
    } else if (status === 429) {
      ElMessage.warning(t('newsMgmt.aiRateLimited'));
    } else {
      ElMessage.error(backendError || t('newsMgmt.aiFailed'));
    }
  } finally {
    aiBusy.value = '';
  }
};

const imageFile = ref(null);
const coverPreview = ref('');
const clearImage = ref(false);

const rules = {
  title: [
    { required: true, message: t('news.validateTitle'), trigger: 'blur' },
    { min: 5, max: 200, message: t('news.validateTitleLen200'), trigger: 'blur' },
  ],
  category: [{ required: true, message: t('news.validateCategory'), trigger: 'change' }],
  content: [
    { required: true, message: t('news.validateContent'), trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        const text = (value || '').replace(/<[^>]*>/g, '').trim();
        if (text.length < 10) {
          callback(new Error(t('newsMgmt.contentMin')));
        } else {
          callback();
        }
      },
      trigger: 'blur',
    },
  ],
};

const resetForm = () => {
  Object.assign(form, {
    id: null,
    title: '',
    // 第 404 批：英文字段清空（新建时为空；编辑时 handleEdit 会回填）
    title_en: '',
    content: '',
    content_en: '',
    category: 'notice',
    source: '',
    source_en: '',
    tags: [],
    is_published: true,
    published_at: null,
    summary: '',
    is_featured: false,
    // 第 401 批
    external_url: '',
    related_pests: [],
  });
  // 新建新闻时"关系为空"是确定的；编辑时 handleEdit 会按响应里有没有该字段覆盖
  relatedPestsKnown.value = true;
  imageFile.value = null;
  coverPreview.value = '';
  clearImage.value = false;
  newsFormRef.value?.clearValidate();
};

const handleCreate = () => {
  formTitle.value = t('newsMgmt.newNews');
  resetForm();
  // 第 401 批：打开弹窗时按需加载病害选项（只拉一次）
  ensurePestOptions();
  dialogVisible.value = true;
};

const handleEdit = (row) => {
  formTitle.value = t('news.edit');
  resetForm();
  // 第 401 批：列表行可能没有关联字段（老后端）；有 related_pests 用 id，
  // 只有 related_pest_details 时用明细里的 id 兜底，两者都没有就标 known=false，
  // 提交时不带 clear_related_pests，避免把后端存量关系误清空。
  relatedPestsKnown.value = Array.isArray(row.related_pests) || Array.isArray(row.related_pest_details);
  const relatedPestIds = Array.isArray(row.related_pests)
    ? toPestIdArray(row.related_pests)
    : toPestIdArray(
      (Array.isArray(row.related_pest_details) ? row.related_pest_details : []).map((pest) => pest?.id),
    );
  Object.assign(form, {
    id: row.id,
    title: row.title || '',
    // 第 404 批：英文标题 / 正文 / 来源（老数据没有该字段时为空串，保存可清空）
    title_en: row.title_en || '',
    content: row.content || '',
    content_en: row.content_en || '',
    category: row.category || 'notice',
    source: row.source || '',
    source_en: row.source_en || '',
    tags: row.tags ? String(row.tags).split(',').filter(Boolean) : [],
    is_published: !!row.is_published,
    published_at: row.published_at || null,
    // 第 399 批：列表行（后端序列化器）带 summary / is_featured；老数据给安全默认值
    summary: row.summary || '',
    is_featured: !!row.is_featured,
    // 第 401 批：原文链接 / 关联病害
    external_url: row.external_url || '',
    related_pests: relatedPestIds,
  });
  coverPreview.value = toAbsoluteMediaUrl(row.image_url || row.image);
  ensurePestOptions();
  dialogVisible.value = true;
};

// ---------- 封面 ----------
const handleImageChange = (uploadFile) => {
  const raw = uploadFile?.raw;
  if (!raw) return;

  if (!raw.type.startsWith('image/')) {
    ElMessage.error(t('msg.imageOnly'));
    return;
  }
  if (raw.size / 1024 / 1024 >= 5) {
    ElMessage.error(t('msg.imageTooLarge5'));
    return;
  }

  imageFile.value = raw;
  clearImage.value = false;

  const reader = new FileReader();
  reader.onload = (event) => {
    coverPreview.value = event.target.result;
  };
  reader.readAsDataURL(raw);
};

const removeCover = () => {
  imageFile.value = null;
  coverPreview.value = '';
  clearImage.value = true;
};

// ---------- 提交 / 状态 / 删除 ----------
const submitForm = async () => {
  if (!newsFormRef.value) return;

  try {
    await newsFormRef.value.validate();
  } catch {
    return;
  }

  submitting.value = true;
  try {
    const payload = {
      title: form.title.trim(),
      // 第 404 批：英文字段始终带键 —— 空串=清空（用户删掉译文后保存要真的清掉），
      // buildNewsFormData 只在键存在时 append，所以这里的键不能省。
      title_en: (form.title_en || '').trim(),
      content: form.content,
      content_en: (form.content_en || '').trim(),
      category: form.category,
      source: form.source.trim(),
      source_en: (form.source_en || '').trim(),
      tags: form.tags,
      is_published: form.is_published,
      published_at: form.published_at || null,  // 第 38 批：定时发布
      // 第 399 批：摘要（空串 = 清空）与精选开关；buildNewsFormData 按后端
      // multipart 约定打成 'true'/'false'，published_at=null 会打成空串（清空定时）
      summary: form.summary || '',
      is_featured: !!form.is_featured,
      // 第 401 批：原文链接（空串 = 清空）
      external_url: (form.external_url || '').trim(),
      clear_image: clearImage.value,
    };

    // 第 401 批：关联病害只在"知道后端已有值"时才提交。
    // 老后端没有该字段，若照常提交空数组 + clear_related_pests=true，
    // 保存一次就会把后端存量的关联关系误清空。
    if (relatedPestsKnown.value) {
      const relatedPestIds = toPestIdArray(form.related_pests);
      payload.related_pests = relatedPestIds;
      // multipart 无法表达空数组：清空用独立开关；非空传 false 表示以本次列表为准
      payload.clear_related_pests = relatedPestIds.length === 0;
    }

    if (form.id) {
      await updateNews(form.id, payload, imageFile.value);
      ElMessage.success(t('newsMgmt.updatedOk'));
    } else {
      await createNews(payload, imageFile.value);
      ElMessage.success(t('newsMgmt.createdOk'));
    }

    dialogVisible.value = false;
    await fetchData();
    // 第 403 批：新增/编辑会改变看板统计，顺手刷新（失败静默）
    loadNewsStats();
  } catch (error) {
    console.error('保存新闻失败:', error);
    ElMessage.error(formatNewsError(error, t('msg.savingFailedRetry')));
  } finally {
    submitting.value = false;
  }
};

const togglePublishStatus = async (row) => {
  const nextStatus = !row.is_published;
  try {
    const updated = await toggleNewsPublished(row.id, nextStatus);
    // 以服务端返回的状态为准（而不是本地取反），避免出现
    // "界面显示已下架、库里其实仍是已发布"这种难以察觉的不一致
    const actual = typeof updated?.is_published === 'boolean' ? updated.is_published : nextStatus;
    row.is_published = actual;
    ElMessage.success(t('newsMgmt.publishToggled', { action: actual ? t('newsMgmt.publishedAction') : t('newsMgmt.unpublishedAction') }));
    // 操作后重新拉取列表，确保管理端看到的与后端完全一致
    await fetchData();
    // 第 403 批：上下架会改变看板的已发布/草稿数
    loadNewsStats();
  } catch (error) {
    console.error('更新新闻状态失败:', error);
    ElMessage.error(formatNewsError(error, t('msg.operationFailedRetry')));
    await fetchData();
  }
};

const handleDelete = async (id) => {
  try {
    await deleteNews(id);
    ElMessage.success(t('msg.deleteOk'));
    // 删除最后一条时回退一页
    if (newsList.value.length === 1 && pagination.currentPage > 1) {
      pagination.currentPage -= 1;
    }
    await fetchData();
    // 第 403 批：删除会改变看板的分类占比/标签云
    loadNewsStats();
  } catch (error) {
    console.error('删除新闻失败:', error);
    ElMessage.error(formatNewsError(error, t('msg.deleteFailedRetry')));
  }
};

// ---------- 工具 ----------
const formatDate = (value) => {
  if (!value) return '-';
  try {
    return format(new Date(value), 'yyyy-MM-dd HH:mm');
  } catch {
    return value;
  }
};

// ============================================================================
// 深链：由旧路由 `/news/create`、`/news/:id/edit` 重定向进来（第 121 批）
// ----------------------------------------------------------------------------
// 那两条历史深链过去是渲染**农户端外观**的行业动态页 + 弹窗，而它们都要管理员权限 ——
// 等于让管理员在管理动作上看到农户那张脸。现在它们重定向到这里，并带上：
//     ?action=create            打开"新增新闻"弹窗
//     ?action=edit&id=<新闻 id>  拉取该新闻并打开"编辑新闻"弹窗
// 处理完把 query 清掉（router.replace）：否则管理员关掉弹窗再点别的行时，
// 地址栏里还挂着 action=create，刷新一下弹窗又自己冒出来。
// ============================================================================
const route = useRoute();
const router = useRouter();

/** 第 403 批：看板「阅读量 Top」点击跳新闻详情 */
const goToNewsDetail = (id) => {
  if (!id) return;
  router.push({ name: 'news-detail', params: { id } });
};

const openFromQuery = async () => {
  const action = String(route.query.action || '');
  if (!action) return;

  if (action === 'create') {
    handleCreate();
  } else if (action === 'edit') {
    const id = Number(route.query.id);
    if (!id) {
      ElMessage.warning(t('newsMgmt.editMissingId'));
    } else {
      try {
        const detail = await fetchNewsDetail(id);
        handleEdit(detail);
      } catch (error) {
        // 文章可能已被删掉（老书签）—— 明说，不要静默什么都不发生
        ElMessage.error(formatNewsError(error, t('newsMgmt.editLoadFailed')));
      }
    }
  }

  router.replace({ name: 'news-management', query: {} });
};

onMounted(async () => {
  // 第 403 批：看板与列表并行加载（loadNewsStats 内部已兜底，失败不影响列表）
  loadNewsStats();
  await fetchData();
  await openFromQuery();
});</script>

<style scoped>
.news-management {
  --nm-primary: #2a7f53;
  --nm-primary-dark: #1f6343;
  --nm-border: #e6ece9;
  --nm-text: #22312b;
  --nm-muted: #7b8c99;

  max-width: 1400px;
  margin: 0 auto;
  /* 第 29 批：整页套 .tinted-page（浅绿工作区底），这里保留工作区自身的内边距 */
  padding: 22px 22px 34px;
  color: var(--nm-text);
}

/* 第 117 批：删掉了 `.news-management > .back-button` 的间距规则（返回按钮已随管理后台外壳一起移除） */

/* 说明（第 29 批）：页头已改用全局 .admin-hero 的深绿实底样式，
   原来这里的 .page-head 浅绿渐变已删除 —— 浅绿页头铺在浅绿工作区底上会糊成一片。 */

/* 深绿页头上的白色按钮（配合全局 .btn-on-brand，这里只保留尺寸与圆角） */
.add-btn {
  border-radius: 12px;
  padding: 20px 22px;
}

.add-btn:hover {
  transform: translateY(-1px);
}

/* 筛选栏 */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin: 18px 0;
  padding: 16px 20px;
  /* 第 28 批：纯白改成极浅的绿底渐变，和统计卡形成层次 */
  background: linear-gradient(180deg, #ffffff, #eef8f2);
  border: 1px solid var(--brand-200, #bfe3cd);
  border-radius: 16px;
  box-shadow: 0 1px 2px rgba(19, 58, 41, 0.05);
}

.filter-keyword {
  width: 280px;
}

.filter-select {
  width: 150px;
}

.filter-total {
  margin-left: auto;
  font-size: 13px;
  color: var(--nm-muted);
}

/* 表格卡片 */
.table-card {
  border-radius: 18px;
  border: 1px solid var(--brand-200, #bfe3cd);
  overflow: hidden;
  box-shadow: 0 10px 30px rgba(31, 99, 67, 0.08);
}

/* 卡片内边距交给 .panel-head / .panel-body，避免头条被 8px 内边距挤住 */
.table-card :deep(.el-card__body) {
  padding: 0;
}

/* 头条右侧的说明文字 */
.panel-hint {
  font-size: 12px;
  color: var(--ink-500);
}

.cover-cell {
  width: 84px;
  height: 56px;
  border-radius: 10px;
  overflow: hidden;
  background: #f4f8f6;
  display: flex;
  align-items: center;
  justify-content: center;
}

.cover-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.cover-placeholder {
  color: #b6c6be;
  font-size: 18px;
}

.title-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.title-text {
  font-weight: 600;
  color: var(--nm-text);
  line-height: 1.5;
}

.title-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--nm-muted);
}

.table-empty {
  padding: 28px 0;
  color: var(--nm-muted);
  text-align: center;
}

.table-empty i {
  font-size: 26px;
  display: block;
  margin-bottom: 6px;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  padding: 14px 0 0;
}

/* 表单（第 33 批：封面改成主题里的 .upload-tile 瓦片，
   原来的 .cover-preview / .cover-uploader-empty / .cover-tips / .dialog-footer
   已随旧弹窗结构一起删除） */
.editor-wrap {
  width: 100%;
}

.editor-wrap :deep(.ql-container) {
  min-height: 220px;
}

.cover-field {
  width: 100%;
}

.cover-uploader {
  display: block;
  width: 100%;
}

.cover-uploader :deep(.el-upload) {
  display: block;
  width: 100%;
  border: none;
  overflow: visible;
}

.cover-tile {
  width: 100%;
}

/* 第 401 批：标题 meta 行的原文外链小图标 */
.title-ext-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: var(--radius-xs);
  color: var(--brand-600);
  font-size: 11px;
  transition: background var(--dur) var(--ease), color var(--dur) var(--ease);
}

.title-ext-link:hover {
  background: var(--brand-50);
  color: var(--brand-800);
}

@media (max-width: 768px) {
  .filter-keyword,
  .filter-select {
    width: 100%;
  }

  .filter-total {
    margin-left: 0;
  }
}

/* ================= 第 403 批：新闻数据看板 ================= */
.news-dashboard {
  margin: 4px 0 18px;
}

.dashboard-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.dashboard-head-text h3 {
  margin: 0 0 4px;
  font-size: 18px;
  font-weight: 800;
  color: var(--ink-900);
}

.dashboard-head-text p {
  margin: 0;
  font-size: 12.5px;
  color: var(--ink-500);
}

.dashboard-range {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.dashboard-range-label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink-500);
}

.dashboard-stats {
  margin: 0 0 14px;
  /* 6 张卡在桌面排 3 列 × 2 行（比 auto-fit 的 5+1 更均衡；375px 收成 2 列） */
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.dashboard-skeleton {
  padding: 16px 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: linear-gradient(180deg, #f5fcf8 0%, #ffffff 62%);
}

.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 14px;
}

/* 图表容器固定高度：切换 7/30/90 天时图表不会跳、也不把整页撑高 */
.dashboard-chart-body {
  position: relative;
  height: 240px;
}

.dashboard-list-body {
  min-height: 240px;
}

.dashboard-tag-body {
  min-height: 240px;
}

.dashboard-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 100%;
  min-height: 180px;
  color: var(--ink-400);
  font-size: 13px;
}

.dashboard-empty i {
  font-size: 26px;
  opacity: 0.6;
}

.dashboard-empty--compact {
  min-height: 160px;
}

/* 阅读量 Top */
.top-viewed-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.top-viewed-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-width: 0;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color var(--dur) var(--ease), background var(--dur) var(--ease);
}

.top-viewed-item:hover {
  border-color: var(--brand-300);
  background: var(--brand-50);
}

.top-viewed-rank {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--ink-100);
  color: var(--ink-500);
  font-size: 12px;
  font-weight: 700;
}

.top-viewed-rank.is-1 { background: linear-gradient(135deg, #f0a94a, #d9822b); color: #fff; }
.top-viewed-rank.is-2 { background: linear-gradient(135deg, #9fb4c7, #7b8fa3); color: #fff; }
.top-viewed-rank.is-3 { background: linear-gradient(135deg, #cd9a72, #a9764c); color: #fff; }

.top-viewed-title {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-800);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.top-viewed-views {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--ink-400);
}

/* 标签云：字号/深浅按出现次数区分 */
.tag-cloud {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px 10px;
}

.tag-cloud-item {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  padding: 4px 12px;
  border: 1px solid var(--brand-200);
  border-radius: var(--radius-pill);
  background: var(--brand-50);
  color: var(--brand-700);
  font-weight: 600;
  line-height: 1.5;
}

.tag-cloud-item em {
  font-style: normal;
  font-size: 10.5px;
  font-weight: 700;
  opacity: 0.75;
}

@media (max-width: 900px) {
  .dashboard-grid {
    grid-template-columns: 1fr;
  }

  .dashboard-chart-body {
    height: 220px;
  }
}

@media (max-width: 768px) {
  .dashboard-range {
    width: 100%;
  }

  /* 375px：统计卡固定 2 列，6 张卡排 3 行（不再按 minmax 自适应成 1 列） */
  .dashboard-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 480px) {
  .dashboard-stats {
    gap: 8px;
  }

  .stat-tile {
    padding: 12px;
  }

  .top-viewed-item {
    padding: 8px;
  }
}

/* 第 403 批：375px 实测发现本页多出 19px 横向滚动条 —— 根因不在看板，而是
   `.tinted-page::after` 那个 250×250 的右侧圆形水印用了 `right: -34px`，故意
   探出容器装饰边缘；桌面端看着是设计，手机端就变成"整页可以左右晃"。
   这里只在窄屏把它裁掉（overflow-x: clip 不新建滚动容器，也不影响纵向 sticky），
   桌面端保持原样。同类页面（也用 .tinted-page）若要做移动端，可复用这一行。 */
@media (max-width: 768px) {
  .news-management {
    overflow-x: clip;
  }
}

/* ================= 第 404 批：AI 辅助按钮 / 字段 label 行 ================= */
.form-label-row {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  max-width: 100%;
}

/* 与表单里的 .field-hint 同一套轻量观感：虚线胶囊，hover 变实线 */
.ai-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 10px;
  border: 1px dashed var(--brand-300);
  border-radius: var(--radius-pill);
  background: var(--brand-50);
  color: var(--brand-700);
  font-family: inherit;
  font-size: 11.5px;
  font-weight: 600;
  line-height: 18px;
  white-space: nowrap;
  cursor: pointer;
  transition: border-color var(--dur) var(--ease), background var(--dur) var(--ease),
    opacity var(--dur) var(--ease);
}

.ai-btn:hover:not(:disabled) {
  border-style: solid;
  border-color: var(--brand-500);
  background: var(--brand-100);
}

.ai-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.ai-btn i {
  font-size: 11px;
}

@media (max-width: 480px) {
  /* 375px：label 行允许换行，AI 按钮不会把字段标题挤出弹窗 */
  .form-label-row {
    gap: 6px;
  }

  .ai-btn {
    padding: 2px 8px;
    font-size: 11px;
  }
}
</style>
