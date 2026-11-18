<template>
  <div class="news-container">
    <!-- 新闻头部 -->
    <div class="news-header">
      <div class="header-content">
        <!-- 第 33 批：原来这里是 `el-icon-news` —— Element Plus 2 已经没有图标字体了，
             这类类名不会渲染出任何字形（实测 ::before content 为 none、宽度 0），
             下面这些图标统一换成 Font Awesome。 -->
        <h1><i class="fas fa-newspaper"></i> {{ t('news.title') }}</h1>
        <p class="header-desc">{{ t('news.subtitle') }}</p>
      </div>
      <div class="header-actions" v-if="isAdmin">
        <el-button
          type="primary"
          @click="goToAddNews"
          class="add-news-btn"
        >
          <i class="fas fa-plus"></i> {{ t('news.addNews') }}
        </el-button>
      </div>
    </div>

    <!-- 分类 / 排序 / 时间筛选（第 399 批 · P0-2：分类按钮旁补排序与时间范围，
         热门标签条单独占一行（flex-basis:100%），避免把第一行挤乱） -->
    <div class="filter-container">
      <div class="filter-left">
        <el-radio-group v-model="activeCategory" size="default" @change="handleFilterChange">
          <el-radio-button value="">{{ t('news.all') }}</el-radio-button>
          <el-radio-button v-for="category in categories" :key="category.value" :value="category.value">
            {{ category.label }}
          </el-radio-button>
        </el-radio-group>

        <!-- 第 402 批：分类订阅开关（仅登录用户、且选中具体分类时出现）。
             它是独立 button，不放进 el-radio-group，所以点击不会触发筛选/翻页。 -->
        <button
          v-if="isLoggedIn && activeCategory"
          type="button"
          class="subscribe-btn"
          :class="{ 'is-subscribed': categorySubscribed }"
          :disabled="categorySubscriptionLoading || categorySubscriptionChecking"
          :aria-pressed="categorySubscribed"
          :title="categorySubscribed ? t('news.unsubscribeCategory') : t('news.subscribeCategory')"
          @click="toggleCategorySubscription"
        >
          <i
            :class="categorySubscriptionLoading || categorySubscriptionChecking
              ? 'fas fa-spinner fa-spin'
              : categorySubscribed ? 'fas fa-bell' : 'fas fa-bell-plus'"
          ></i>
          {{ categorySubscribed ? t('news.subscribedCategory') : t('news.subscribeCategory') }}
        </button>

        <el-select
          v-model="publishStatus"
          :placeholder="t('news.publishStatus')"
          clearable
          style="width: 120px; margin-left: 10px;"
          @change="handleFilterChange"
          @clear="handleFilterChange"
          v-if="isAdmin"
        >
          <el-option :label="t('news.published')" value="published" />
          <el-option :label="t('news.unpublished')" value="unpublished" />
        </el-select>

        <!-- 第 399 批：排序（recent / hot / oldest）与时间范围（all / 7d / 30d）。
             两个值都会原样进 fetchNews 的 params，任一变化都重置到第 1 页。 -->
        <el-select
          v-model="ordering"
          class="filter-select"
          :aria-label="t('news.orderingLabel')"
          @change="handleFilterChange"
        >
          <el-option :label="t('news.orderingRecent')" value="recent" />
          <el-option :label="t('news.orderingHot')" value="hot" />
          <el-option :label="t('news.orderingOldest')" value="oldest" />
        </el-select>

        <el-select
          v-model="dateRange"
          class="filter-select"
          :aria-label="t('news.dateRangeLabel')"
          @change="handleFilterChange"
        >
          <el-option :label="t('news.dateRangeAll')" value="all" />
          <el-option :label="t('news.dateRange7d')" value="7d" />
          <el-option :label="t('news.dateRange30d')" value="30d" />
        </el-select>
      </div>

      <div class="search-box">
        <el-input
          v-model="searchQuery"
          class="news-search-input"
          :placeholder="t('news.searchPlaceholder')"
          clearable
          @clear="handleSearch"
          @keyup.enter="handleSearch"
        >
          <template #prepend>
            <el-select v-model="searchType" :placeholder="t('news.searchType')" style="width: 110px">
              <el-option :label="t('news.searchByTitle')" value="title" />
              <el-option :label="t('news.searchByContent')" value="content" />
              <el-option :label="t('news.all')" value="all" />
            </el-select>
          </template>
          <template #append>
            <el-button @click="handleSearch"><i class="fas fa-search"></i></el-button>
          </template>
        </el-input>
      </div>

      <!-- 第 399 批：热门标签多选条（标签聚合来自 /news/tags/，前端不硬编码）。
           后端还没上这个接口时 fetchNewsTags 会失败 → hotTags 保持 []，
           这里显示「暂无标签」，筛选功能其余部分不受影响。 -->
      <div class="hot-tags-bar">
        <span class="hot-tags-label">
          <i class="fas fa-tags"></i> {{ t('news.hotTagsLabel') }}
        </span>
        <div class="hot-tags-list" v-if="hotTags.length">
          <button
            v-for="tag in hotTags"
            :key="tag.name"
            type="button"
            class="hot-tag"
            :class="{ 'is-active': selectedTags.includes(tag.name) }"
            :aria-pressed="selectedTags.includes(tag.name)"
            @click="toggleTag(tag.name)"
          >
            {{ tag.name }}
            <span class="hot-tag-count">{{ tag.count }}</span>
          </button>
        </div>
        <span v-else class="hot-tags-empty">{{ t('news.noTags') }}</span>
        <el-button
          v-if="selectedTags.length"
          text
          size="small"
          class="clear-tags-btn"
          @click="clearTags"
        >
          <i class="fas fa-xmark"></i> {{ t('news.clearTags') }}
        </el-button>
      </div>
    </div>

    <div class="news-list-container">
      <!-- 第 378 批：加载中给卡片骨架（与真实 .news-card 同列宽、同封面比例、同内边距）。
           列表只有 fetchNews() 一个数据源，newsList 在请求返回前恒为空，
           因此这里就是"首屏加载中"的完整画面；加载完成后由下方真实列表 / 空态接管。 -->
      <div
        v-if="listLoading && newsList.length === 0"
        class="news-skeleton"
        role="status"
        :aria-label="t('common.loading')"
      >
        <el-skeleton v-for="i in 3" :key="i" animated class="skeleton-card">
          <template #template>
            <div class="skeleton-content">
              <el-skeleton-item variant="image" class="skeleton-cover" />
              <div class="skeleton-body">
                <el-skeleton-item variant="h3" style="width: 78%" />
                <el-skeleton-item variant="text" style="width: 100%" />
                <el-skeleton-item variant="text" style="width: 62%" />
              </div>
            </div>
          </template>
        </el-skeleton>
      </div>
      <!-- News List -->
      <div class="news-list">
        <!-- 第 399 批 · P0-1：头条精选区。只在第 1 页、且拿到 featured 段时出现；
             后端已把这几条从 results/count 里剔除，所以下方网格不会重复展示。
             老后端没有 featured 字段 → featuredList 恒为 []，整块不渲染。 -->
        <section
          v-if="currentPage === 1 && featuredList.length > 0 && !listLoading"
          class="featured-section"
          :aria-label="t('news.featuredTitle')"
        >
          <div class="featured-head">
            <h2><i class="fas fa-star"></i> {{ t('news.featuredTitle') }}</h2>
            <span class="featured-head-count">{{ featuredList.length }}</span>
          </div>
          <div class="featured-grid" :class="{ 'is-single': featuredList.length === 1 }">
            <article
              v-for="item in featuredList"
              :key="item.id"
              class="featured-card"
              @click="goToNewsDetail(item.id)"
            >
              <div class="featured-cover">
                <el-image
                  v-if="item.image_url"
                  :src="getFullImageUrl(item.image_url)"
                  fit="cover"
                  class="featured-cover-img"
                >
                  <template #error>
                    <div class="image-slot">
                      <i class="fas fa-image"></i>
                    </div>
                  </template>
                </el-image>
                <div v-else class="no-image">
                  <el-icon><Picture /></el-icon>
                  <span>{{ t('news.noImage') }}</span>
                </div>
                <div class="news-category" v-if="item.category">
                  {{ getCategoryLabel(item.category) }}
                </div>
                <div class="featured-flag">
                  <i class="fas fa-star"></i> {{ t('news.featuredBadge') }}
                </div>
              </div>
              <div class="featured-body">
                <h3 class="featured-title">{{ localizedField(item, 'title') }}</h3>
                <p class="featured-summary">{{ summaryOf(item) }}</p>
                <div class="featured-meta">
                  <span v-if="item.source">
                    <!-- 第 401 批：来源命中官方白名单时加「官方」徽标（仅展示层，不新增后端字段） -->
                    <span v-if="isOfficialSource(item)" class="official-badge">
                      <i class="fas fa-circle-check"></i> {{ t('news.officialBadge') }}
                    </span>
                    <i class="fas fa-building-columns"></i> {{ localizedField(item, 'source') }}
                  </span>
                  <span>
                    <i class="fas fa-clock"></i> {{ formatDate(item.created_at) }}
                  </span>
                  <span v-if="item.views !== undefined && item.views !== null">
                    <i class="fas fa-eye"></i> {{ t('forum.readsShort', { count: item.views }) }}
                  </span>
                  <!-- 第 401 批：原文外链。@click.stop 防止触发整张卡片的"进详情"跳转 -->
                  <a
                    v-if="item.external_url"
                    class="news-external"
                    :href="item.external_url"
                    target="_blank"
                    rel="noopener noreferrer"
                    @click.stop
                  >
                    <i class="fas fa-arrow-up-right-from-square"></i> {{ t('news.externalLink') }}
                  </a>
                </div>
                <!-- 第 401 批：关联病害 chip（最多 3 个 + N），点击直达病害详情 -->
                <div v-if="relatedPestsOf(item).length" class="news-pests featured-pests">
                  <button
                    v-for="pest in visiblePests(item)"
                    :key="pest.id"
                    type="button"
                    class="pest-chip"
                    @click.stop="goToPestDetail(pest)"
                  >
                    <i class="fas fa-leaf"></i> {{ pestChipLabel(pest) }}
                  </button>
                  <span
                    v-if="relatedPestsOf(item).length > MAX_CARD_PESTS"
                    class="pest-chip pest-chip-more"
                    :title="t('news.pestsMore', { count: relatedPestsOf(item).length - MAX_CARD_PESTS })"
                  >
                    +{{ relatedPestsOf(item).length - MAX_CARD_PESTS }}
                  </span>
                </div>
                <span class="featured-read-more">
                  {{ t('news.readMore') }} <i class="fas fa-arrow-right"></i>
                </span>
              </div>
            </article>
          </div>
        </section>

        <div class="news-grid">
          <el-card
            v-for="newsItem in newsList"
            :key="newsItem.id"
            class="news-card"
            shadow="hover"
            @click="goToNewsDetail(newsItem.id)"
          >
            <div class="news-content">
              <div class="news-image">
                <el-image
                  v-if="newsItem.image_url"
                  :src="getFullImageUrl(newsItem.image_url)"
                  :preview-src-list="[getFullImageUrl(newsItem.image_url)]"
                  fit="cover"
                  class="news-image"
                  style="width: 100%; height: 200px; cursor: pointer;"
                  @click="$event.stopPropagation()"
                >
                  <template #error>
                    <div class="image-slot">
                      <i class="fas fa-image"></i>
                    </div>
                  </template>
                </el-image>
                <div v-else class="no-image">
                  <el-icon><Picture /></el-icon>
                  <span>{{ t('news.noImage') }}</span>
                </div>
                <div class="news-category" v-if="newsItem.category">
                  {{ getCategoryLabel(newsItem.category) }}
                </div>
                <!-- 第 399 批 · P0-4：封面层的精选标记（分类角标之外） -->
                <div class="news-featured-flag" v-if="newsItem.is_featured">
                  <i class="fas fa-star"></i> {{ t('news.featuredBadge') }}
                </div>
              </div>
              <div class="news-details">
                <h2 class="news-title">{{ localizedField(newsItem, 'title') }}</h2>
                <!-- 第 399 批 · P0-3：优先后端摘要（summary），为空再由 summaryOf 回退正文 -->
                <div class="news-summary">
                  {{ summaryOf(newsItem) }}
                </div>
                <!-- 第 399 批 · P0-4：卡片分三层——封面 / 标题+摘要 / meta + 标签 + 操作区，
                     meta 从标题下方移到这里，避免小屏时来源/日期/阅读量与标签挤在一起 -->
                <div class="news-meta">
                  <span class="news-source" v-if="newsItem.source">
                    <!-- 第 401 批：官方来源徽标（关键词包含匹配，见 OFFICIAL_SOURCE_KEYWORDS） -->
                    <span v-if="isOfficialSource(newsItem)" class="official-badge">
                      <i class="fas fa-circle-check"></i> {{ t('news.officialBadge') }}
                    </span>
                    <i class="fas fa-building-columns"></i> {{ localizedField(newsItem, 'source') }}
                  </span>
                  <span class="news-date">
                    <i class="fas fa-clock"></i> {{ formatDate(newsItem.created_at) }}
                  </span>
                  <span class="news-views" v-if="newsItem.views !== undefined">
                    <i class="fas fa-eye"></i> {{ t('forum.readsShort', { count: newsItem.views }) }}
                  </span>
                  <!-- 第 401 批：原文外链（新标签页 + noopener；stopPropagation 避免进详情页） -->
                  <a
                    v-if="newsItem.external_url"
                    class="news-external"
                    :href="newsItem.external_url"
                    target="_blank"
                    rel="noopener noreferrer"
                    @click.stop
                  >
                    <i class="fas fa-arrow-up-right-from-square"></i> {{ t('news.externalLink') }}
                  </a>
                </div>
                <!-- 第 401 批：关联病害 chip（最多 3 个，其余 +N；点击直达百科详情） -->
                <div v-if="relatedPestsOf(newsItem).length" class="news-pests">
                  <button
                    v-for="pest in visiblePests(newsItem)"
                    :key="pest.id"
                    type="button"
                    class="pest-chip"
                    @click.stop="goToPestDetail(pest)"
                  >
                    <i class="fas fa-leaf"></i> {{ pestChipLabel(pest) }}
                  </button>
                  <span
                    v-if="relatedPestsOf(newsItem).length > MAX_CARD_PESTS"
                    class="pest-chip pest-chip-more"
                    :title="t('news.pestsMore', { count: relatedPestsOf(newsItem).length - MAX_CARD_PESTS })"
                  >
                    +{{ relatedPestsOf(newsItem).length - MAX_CARD_PESTS }}
                  </span>
                </div>
                <div class="news-footer">
                  <div class="news-tags">
                    <el-tag
                      v-for="(tag, index) in (Array.isArray(newsItem.tags) ? newsItem.tags : [newsItem.tag].filter(Boolean))"
                      :key="index"
                      size="mini"
                      :type="getTagType(tag)"
                      style="margin-right: 5px; margin-bottom: 5px;"
                    >
                      {{ tag }}
                    </el-tag>
                    <el-tag
                      v-if="!newsItem.is_published"
                      size="mini"
                      type="info"
                      style="margin-left: 5px;"
                    >
                      {{ t('news.unpublished') }}
                    </el-tag>
                  </div>
                  <!-- 第 399 批 · P0-4：操作区默认隐藏（hover / focus-within 才出现），
                       管理员始终可见（.is-admin），触屏与窄屏由样式强制常显 -->
                  <div class="news-actions" :class="{ 'is-admin': isAdmin }">
                    <el-button
                      v-if="isAdmin"
                      type="text"
                      size="small"
                      @click.stop="editNews(newsItem)"
                    >
                      <el-icon><Edit /></el-icon> {{ t('news.edit') }}
                    </el-button>
                    <el-button
                      v-if="isAdmin"
                      type="text"
                      size="small"
                      @click.stop="confirmDelete(newsItem.id)"
                    >
                      <el-icon><Delete /></el-icon> {{ t('news.delete') }}
                    </el-button>
                    <el-button
                      type="text"
                      class="read-more"
                      @click.stop="goToNewsDetail(newsItem.id)"
                    >
                      {{ t('news.readMore') }} <i class="fas fa-arrow-right"></i>
                    </el-button>
                  </div>
                </div>
              </div>
            </div>
          </el-card>
        </div>

        <el-empty v-if="!listLoading && newsList.length === 0" :description="t('news.noNews')" />

        <div class="pagination" v-if="total > 0">
          <el-pagination
            v-model:currentPage="currentPage"
            v-model:page-size="pageSize"
            :page-sizes="[5, 10, 20, 50]"
            layout="total, sizes, prev, pager, next, jumper"
            :total="total"
            :pager-count="5"
            @size-change="handleSizeChange"
            @current-change="handleCurrentChange"
          >
            <template #default>
              <span>{{ t('common.totalItems', { count: total }) }}</span>
            </template>
          </el-pagination>
        </div>
      </div>
    </div>

    <!-- 第 31 批：新闻列表下面原来直接就是页脚，补一块"怎么用好行业动态"的说明 -->
    <!-- 第 63 批：卡片内容改由脚本 computed 生成，随语言切换 -->
    <PageExtras
      icon="fas fa-newspaper"
      :title="t('news.guideTitle')"
      :subtitle="t('news.guideSubtitle')"
      :items="guideItems"
    />

    <!-- Add/Edit News Dialog（第 33 批：改成"深绿头条 + 分段表单 + 底部操作条"）
         第 399 批：width 改用 CSS min() —— 手机（375px）上固定 680px 会让弹窗右侧
         超出屏幕且关不掉，而 el-dialog 的宽度是内联 style，页面里的 scoped 媒体查询
         覆盖不到（元素被 teleport 到 body）。min(680px, calc(100vw - 24px)) 在桌面
         仍是 680px，窄屏自动收成"屏宽 - 24px"。 -->
    <el-dialog
      v-model="showAddDialog"
      width="min(680px, calc(100vw - 24px))"
      top="6vh"
      :close-on-click-modal="false"
      class="form-dialog"
    >
      <template #header>
        <div class="form-dialog-head">
          <span class="form-dialog-head-icon">
            <i :class="editingNews ? 'fas fa-pen-to-square' : 'fas fa-plus'"></i>
          </span>
          <div>
            <h3>{{ editingNews ? t('news.dialogEditTitle') : t('news.dialogCreateTitle') }}</h3>
            <p>
              {{ editingNews
                ? t('news.dialogEditHint')
                : t('news.dialogCreateHint') }}
            </p>
          </div>
        </div>
      </template>

      <div class="form-dialog-body">
        <el-form :model="newsForm" :rules="rules" ref="newsFormRef" label-width="0" label-position="top">
          <!-- 基本信息 -->
          <section class="form-section">
            <div class="form-section-head">
              <i class="fas fa-circle-info"></i>
              <h4>{{ t('news.basicInfo') }}</h4>
              <span class="section-hint">{{ t('news.basicInfoHint') }}</span>
            </div>

            <el-form-item :label="t('news.fieldTitle')" prop="title">
              <el-input
                v-model="newsForm.title"
                maxlength="200"
                show-word-limit
                :placeholder="t('news.fieldTitlePlaceholder')"
              />
            </el-form-item>

            <el-row :gutter="16">
              <el-col :xs="24" :sm="12">
                <el-form-item :label="t('news.fieldCategory')" prop="category">
                  <el-select v-model="newsForm.category" :placeholder="t('news.fieldCategoryPlaceholder')" style="width: 100%">
                    <el-option
                      v-for="item in categories"
                      :key="item.value"
                      :label="item.label"
                      :value="item.value"
                    />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :xs="24" :sm="12">
                <el-form-item :label="t('news.fieldSource')" prop="source">
                  <el-input v-model="newsForm.source" :placeholder="t('news.fieldSourcePlaceholder')" />
                </el-form-item>
              </el-col>
            </el-row>

            <!-- 第 401 批：原文链接 / 关联病害（放在「基本信息」，与来源同组） -->
            <el-form-item :label="t('field.externalUrl')">
              <el-input
                v-model="newsForm.external_url"
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
                v-model="newsForm.related_pests"
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
              <span class="section-hint">{{ t('news.bodyHint') }}</span>
            </div>

            <el-form-item :label="t('news.searchByContent')" prop="content">
              <el-input
                v-model="newsForm.content"
                type="textarea"
                :rows="7"
                resize="none"
                :placeholder="t('news.bodyPlaceholder')"
              />
            </el-form-item>

            <!-- 第 399 批 · P0-3：摘要替代"正文硬截断"；留空时列表仍回退正文 -->
            <el-form-item :label="t('news.fieldSummary')">
              <el-input
                v-model="newsForm.summary"
                type="textarea"
                :rows="2"
                resize="none"
                maxlength="200"
                show-word-limit
                :placeholder="t('news.fieldSummaryPlaceholder')"
              />
            </el-form-item>
          </section>

          <!-- 封面与标签 -->
          <section class="form-section">
            <div class="form-section-head">
              <i class="fas fa-image"></i>
              <h4>{{ t('news.coverSection') }}</h4>
              <span class="section-hint">{{ t('news.coverHint') }}</span>
            </div>

            <el-row :gutter="16">
              <el-col :xs="24" :sm="14">
                <el-form-item :label="t('news.coverLabel')">
                  <el-upload
                    class="tile-uploader"
                    action="#"
                    :show-file-list="false"
                    :before-upload="beforeUpload"
                    :on-change="handleUpload"
                    :auto-upload="false"
                    drag
                  >
                    <div class="upload-tile">
                      <img v-if="newsForm.image_preview" :src="newsForm.image_preview" :alt="t('news.coverPreviewAlt')" />
                      <div v-else class="upload-tile-empty">
                        <i class="fas fa-cloud-arrow-up"></i>
                        <span>{{ t('news.dropOr') }} <em>{{ t('news.clickUpload') }}</em></span>
                        <small>{{ t('news.coverFormats') }}</small>
                      </div>

                      <div v-if="newsForm.image_preview" class="upload-tile-actions">
                        <button type="button" :title="t('news.changeImage')">
                          <i class="fas fa-rotate"></i>
                        </button>
                        <button type="button" :title="t('news.removeImage')" @click.stop="removeImage">
                          <i class="fas fa-trash"></i>
                        </button>
                      </div>
                    </div>
                  </el-upload>
                </el-form-item>
              </el-col>

              <el-col :xs="24" :sm="10">
                <el-form-item :label="t('news.tagLabel')" prop="tags">
                  <el-select
                    v-model="newsForm.tags"
                    multiple
                    filterable
                    allow-create
                    default-first-option
                    :placeholder="t('news.tagPlaceholder')"
                    style="width: 100%"
                  >
                    <el-option
                      v-for="tag in newsForm.tags"
                      :key="tag"
                      :label="tag"
                      :value="tag"
                    />
                  </el-select>
                  <p class="field-hint">{{ t('news.tagHint') }}</p>
                </el-form-item>
              </el-col>
            </el-row>
          </section>

          <!-- 发布设置 -->
          <section class="form-section">
            <div class="form-section-head">
              <i class="fas fa-paper-plane"></i>
              <h4>{{ t('news.publishSection') }}</h4>
            </div>

            <el-form-item :label="t('news.publishStatus')" prop="is_published">
              <el-switch
                v-model="newsForm.is_published"
                :active-text="t('news.published')"
                :inactive-text="t('news.saveUnpublished')"
              />
              <p class="field-hint">
                <i class="fas fa-circle-info"></i>
                {{ t('news.publishHint') }}
              </p>
            </el-form-item>

            <!-- 第 399 批 · P0-1：设为精选后由列表接口放进 featured 段，显示在页面顶部头条区 -->
            <el-form-item :label="t('field.featured')">
              <el-switch v-model="newsForm.is_featured" />
              <p class="field-hint">
                <i class="fas fa-star"></i>
                {{ t('news.featuredHint') }}
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
            <el-button @click="showAddDialog = false">{{ t('common.cancel') }}</el-button>
            <!-- 第 380 批：提交有自己的状态，保存中禁用按钮，且不影响列表骨架屏 -->
            <el-button type="primary" :loading="submitLoading" @click="submitNews">
              <i class="fas fa-check"></i>
              {{ editingNews ? t('news.saveChanges') : t('news.createNews') }}
            </el-button>
          </span>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue';
import { useRouter, useRoute } from 'vue-router';
// 第 33 批：Refresh / UploadFilled / Plus 已改用 Font Awesome 图标，不再需要
import { Picture, Delete, Edit } from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useAuthStore } from '@/stores/auth';
import axios from 'axios';
import { toAbsoluteMediaUrl, formatApiError } from '@/api/http';
import api from '@/api';
// 与管理端「新闻管理」页共用同一套提交逻辑（字段白名单 + multipart 组装 + 错误文案）
import { createNews, updateNews, formatNewsError, fetchNewsTags } from '@/api/news';
// 第 401 批：管理员编辑弹窗的「关联病害」下拉选项（病害百科词条）
import { fetchPestList } from '@/api/pest';
// 第 402 批：分类订阅（状态查询 / 新建 / 取消）—— 接口未上线时按钮按未订阅降级
import {
  checkNewsSubscription,
  createNewsSubscription,
  deleteNewsSubscription,
} from '@/api/newsSubscription';
// 身份读写统一走适配器（sessionStorage 优先），避免"本标签页是 A、请求却带 B 的 token"
import { getToken, clearIdentity } from '@/utils/authStorage';
// 第 31 批：页面底部"怎么用好行业动态"补充信息区
import PageExtras from '@/components/PageExtras.vue';
import { useI18n } from '@/i18n';  // 第 63 批：多语言
import { useLocalized } from '@/utils/localized';  // 第 72 批：新闻正文多语言

const { t } = useI18n();
const { localizedField } = useLocalized();

/** 第 399 批：去掉富文本标签与常见 HTML 实体，得到可安全截断的纯文本 */
const stripHtml = (html) =>
  String(html || '')
    .replace(/<[^>]*>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/\s+/g, ' ')
    .trim();

/**
 * 列表卡片摘要（第 399 批 · P0-3）
 * ------------------------------------------------------------------
 * 优先用后端 `summary`（编辑时人工填写的 1~2 句概括）；没填再回退正文。
 * 回退正文时**先去掉 HTML 标签再截断**：新闻正文是富文本，直接 substring 会把
 * `<p>` / `&nbsp;` 截进卡片（旧实现就是这个毛病）。英文界面走 localizedField
 * 既有的 `_en` 回落规则。只有真的超过 160 字才加省略号，短摘要不会被硬拼出 "..."
 */
const SUMMARY_MAX = 160;
const summaryOf = (item) => {
  if (!item) return '';
  const provided = String(localizedField(item, 'summary') || '').trim();
  const text = provided || stripHtml(localizedField(item, 'content'));
  return text.length > SUMMARY_MAX ? `${text.slice(0, SUMMARY_MAX)}...` : text;
};

/**
 * 第 401 批：官方来源白名单
 * ------------------------------------------------------------------
 * 「来源」是编辑手填的机构名，没有任何"官方认证"字段。读者最需要的是
 * "这条是不是权威渠道发的" —— 与其新增后端字段，不如在展示层按机构名做
 * 关键词包含匹配：命中就在来源前加一个小「官方」徽标。
 *
 * 关键词同时收中英文：内容数据里 source / source_en 都可能是机构名，
 * 匹配时把两者拼起来一起看（见 isOfficialSource），中文界面命中中文、
 * 英文界面命中英文，不会因为切换语言丢掉徽标。
 *
 * 只做"包含"而不要求全等：真实来源常写成「农业农村部种植业管理司」
 * 「中国气象局 · 中央气象台」这类带后缀的形式。
 */
const OFFICIAL_SOURCE_KEYWORDS = [
  '农业农村部',
  '中国气象局',
  '中国农业信息网',
  '国家统计局',
  '海关总署',
  '国家发展改革委',
  '国家发展和改革委员会',
  'Ministry of Agriculture',
  'China Meteorological Administration',
  'National Bureau of Statistics',
  'General Administration of Customs',
  'National Development and Reform Commission',
];

/** 来源是否命中官方白名单（item 可直接传新闻对象，也兼容只传来源字符串） */
const isOfficialSource = (item) => {
  const raw = typeof item === 'string'
    ? item
    : `${item?.source || ''} ${item?.source_en || ''}`;
  const text = raw.toLowerCase();
  if (!text.trim()) return false;
  return OFFICIAL_SOURCE_KEYWORDS.some((keyword) => text.includes(keyword.toLowerCase()));
};

/**
 * 第 401 批：卡片上的关联病害
 * ------------------------------------------------------------------
 * 读接口给的是 `related_pest_details`（轻量条目：id / name / name_en / english_identifier），
 * 写接口用的 `related_pests` 是 id 数组。两个字段都可能缺失（老后端 / 老数据），
 * 这里统一兜底成数组，模板里就不用到处写 `Array.isArray(...)`。
 */
const relatedPestsOf = (item) => (Array.isArray(item?.related_pest_details) ? item.related_pest_details : []);

/** 卡片最多展示 3 个 chip，其余收成 +N */
const MAX_CARD_PESTS = 3;
const visiblePests = (item) => relatedPestsOf(item).slice(0, MAX_CARD_PESTS);

/** chip 文案：名称缺失时退回英文标识符，不渲染空 chip */
const pestChipLabel = (pest) => localizedField(pest, 'name') || pest?.english_identifier || '';

// 第 63 批：底部"怎么用好行业动态"卡片（原来内联在模板里，无法随语言切换）
const guideItems = computed(() => [
  { icon: 'fas fa-filter', title: t('news.guide1'), text: t('news.guide1Desc') },
  { icon: 'fas fa-magnifying-glass', title: t('news.guide2'), text: t('news.guide2Desc') },
  {
    icon: 'fas fa-camera',
    title: t('news.guide3'),
    text: t('news.guide3Desc'),
    more: t('news.guide3Link'),
    to: '/detect',
  },
  {
    icon: 'fas fa-lightbulb',
    title: t('news.guide4'),
    text: t('news.guide4Desc'),
    more: t('news.guide4Link'),
    to: '/feedback',
  },
]);

const router = useRouter();
const route = useRoute();
const authStore = useAuthStore();

// 检查是否是管理员
const isAdmin = computed(() => authStore.isAdmin);

/**
 * 第 402 批：分类订阅
 * ------------------------------------------------------------------
 * 读者选中某个分类时，可以订阅"该分类有新动态就通知我"。几个关键约定：
 *   · 只对**登录用户**展示（`authStore.user` 与页面 isAdmin 同源，不另造一套登录判断）；
 *   · 「全部分类」不是一个可订阅目标 → activeCategory 为空时隐藏按钮；
 *   · 订阅状态由 check 接口确认（不能只看本地，别的标签页/设备可能已订/已退）；
 *   · **序号防竞态**：快速切分类时两个 check 并发，先发的慢响应可能后返回，
 *     不拦的话会把 A 分类的「已订阅」显示到 B 分类上；
 *   · 订阅接口失败只弹一条错误，不影响列表加载（辅助功能不能拖垮主流程）。
 */
const isLoggedIn = computed(() => Boolean(authStore.user));
const categorySubscribed = ref(false);
const categorySubscriptionId = ref(null);
const categorySubscriptionLoading = ref(false);
const categorySubscriptionChecking = ref(false);
let categorySubscriptionSeq = 0;

const resetCategorySubscription = () => {
  categorySubscribed.value = false;
  categorySubscriptionId.value = null;
};

const refreshCategorySubscription = async () => {
  const category = activeCategory.value;
  const seq = ++categorySubscriptionSeq;

  if (!isLoggedIn.value || !category) {
    resetCategorySubscription();
    categorySubscriptionChecking.value = false;
    return;
  }

  // 切到新分类先把旧状态清掉：避免上一个分类的「已订阅」闪现在这个分类上
  resetCategorySubscription();
  categorySubscriptionChecking.value = true;
  try {
    const data = await checkNewsSubscription({ target_type: 'category', category });
    if (seq !== categorySubscriptionSeq) return;
    categorySubscribed.value = data.subscribed;
    categorySubscriptionId.value = data.id;
  } catch (error) {
    if (seq !== categorySubscriptionSeq) return;
    // 接口未上线（404）/ 未登录（401）/ 网络失败：静默降级为「未订阅」，
    // 按钮仍可点（用户点的时候会看到明确的失败提示）
    console.warn('获取分类订阅状态失败（按未订阅处理）:', error);
    resetCategorySubscription();
  } finally {
    if (seq === categorySubscriptionSeq) categorySubscriptionChecking.value = false;
  }
};

const toggleCategorySubscription = async () => {
  const category = activeCategory.value;
  if (!isLoggedIn.value || !category || categorySubscriptionLoading.value) return;

  // 状态说"已订阅"却没有 id：数据不完整，先重新核对，避免误发一次重复订阅（后端会 400）
  if (categorySubscribed.value && !categorySubscriptionId.value) {
    await refreshCategorySubscription();
    return;
  }

  categorySubscriptionLoading.value = true;
  try {
    if (categorySubscribed.value) {
      await deleteNewsSubscription(categorySubscriptionId.value);
      ElMessage.success(t('news.unsubscribeCategoryOk'));
    } else {
      await createNewsSubscription({ target_type: 'category', category });
      ElMessage.success(t('news.subscribeCategoryOk'));
    }
    // 以接口重新核对结果为准（后端可能有上限/去重规则，本地取反不一定对）
    await refreshCategorySubscription();
  } catch (error) {
    console.error('切换分类订阅失败:', error);
    // 重复订阅（400）的中文原因原样显示；英文技术文案由 formatApiError 回落到友好提示
    ElMessage.error(formatApiError(error, t('news.subscribeFailed')));
  } finally {
    categorySubscriptionLoading.value = false;
  }
};

/**
 * 第 401 批：关联病害下拉的选项
 * ------------------------------------------------------------------
 * 按需加载（管理员第一次打开编辑弹窗时）而不是页面初始化就拉：
 *   · 只有管理员才会用到这个下拉，普通读者不该为它多付一次接口请求；
 *   · 病害词条一次最多 100 条，够用；失败时保持空列表（下拉打开是空的），
 *     不弹错误 —— 关联病害是增强项，不能因它阻断"编辑新闻"这条主流程。
 */
const pestOptions = ref([]);
const pestOptionsLoaded = ref(false);
const loadPestOptions = async () => {
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

/** 把接口/表单里的病害 id 归一化成数字数组（后端主键是整数，字符串 id 会让 el-select 匹配不上） */
const toPestIdArray = (value) => {
  if (!Array.isArray(value)) return [];
  return value
    .map((id) => (typeof id === 'number' ? id : Number(id)))
    .filter((id) => Number.isFinite(id) && id > 0);
};

// 第 401 批：后端列表/详情响应里是否有 related_pests 字段。
// 老后端没有这个字段时，提交**不能**带 clear_related_pests=true —— 否则编辑一次
// 就会把后端已有（但前端没拿到）的关联关系误清空。有字段时才按"空数组=清空"处理。
const relatedPestsKnown = ref(true);

// 第 401 批：跳到关联病害的百科详情（点击 chip 时 stopPropagation，不触发卡片跳转）
const goToPestDetail = (pest) => {
  const identifier = pest?.english_identifier;
  if (!identifier) return;
  router.push({ name: 'PestDetail', params: { english_identifier: identifier } });
};


// 第 121 批：`isEditMode` / `isCreateMode` 已删除 —— 那两条历史深链
// （`/news/create`、`/news/:id/edit`）现在重定向进管理后台的新闻管理页，
// 本页只剩下"行业动态列表 + 就地弹窗"这一种身份（新增/编辑都走页面里的按钮）。

// 新闻列表相关
const newsList = ref([]);
// 第 380 批：`loading` 原来被**三处复用** —— 列表加载、详情加载、表单提交。
// 并发 fetchNews（加载中切筛选/翻页/搜索）时，**先返回的那一次**在 finally 里
// 把 loading 置 false，后发的请求还在途、页面却已经认为"加载完成"：
// 骨架屏提前消失、空态"暂无新闻"提前冒出来。这里拆成三个语义独立的状态。
const listLoading = ref(false);    // 列表加载：骨架屏 / 空态的唯一依据
const detailLoading = ref(false);  // 详情加载：编辑前拉单条，绝不碰列表状态
const submitLoading = ref(false);  // 表单提交：保存中禁用按钮，同样不碰列表状态
// 请求序号：每次 fetchNews 领一个号，只有"仍是最新号"的请求才允许落状态。
// 只拆状态还不够 —— 两个 fetchNews 并发时改的是同一个 listLoading，
// 序号才能保证先返回的旧请求不替还在途的新请求收尾。
let listRequestSeq = 0;
const currentPage = ref(1);
const pageSize = ref(10);
const total = ref(0);
const searchQuery = ref('');
const searchType = ref('title');
const activeCategory = ref('');
const publishStatus = ref('');
// 第 399 批 · P0-2：排序 / 时间范围 / 热门标签多选。任一变化都先回到第 1 页再拉列表。
const ordering = ref('recent');
const dateRange = ref('all');
const selectedTags = ref([]);
const hotTags = ref([]);
// 第 399 批 · P0-1：头条段。列表请求带 featured=1 时后端单独返回，
// 且这几条已从 results/count 里剔除；老后端没有该字段时保持 []。
const featuredList = ref([]);

// 表单相关
const showAddDialog = ref(false);
const editingNews = ref(null);
const newsFormRef = ref(null);
const newsForm = ref({
  title: '',
  content: '',
  source: '',
  category: '',
  tags: [],
  image: null,
  is_published: true,
  // 第 399 批：新增字段的后端契约是「缺键不 append」，因此表单里始终显式维护这两个键；
  // summary 清空时提交空串是有意义的（表示清空摘要 → 列表回退正文）
  summary: '',
  is_featured: false,
  // 第 401 批：原文链接 / 关联病害（编辑时从详情接口回填；新建时为空）
  external_url: '',
  related_pests: []
});

// 表单验证规则（文案走 i18n，第 63 批）
const rules = {
  title: [
    { required: true, message: t('news.validateTitle'), trigger: 'blur' },
    { min: 5, max: 100, message: t('news.validateTitleLength'), trigger: 'blur' }
  ],
  content: [
    { required: true, message: t('news.validateContent'), trigger: 'blur' },
    { min: 10, message: t('news.validateContentMin'), trigger: 'blur' }
  ],
  category: [
    { required: true, message: t('news.validateCategory'), trigger: 'change' }
  ]
};

// 新闻分类（标签走 i18n，第 63 批；value 保持后端约定的英文标识）
const categories = computed(() => [
  { label: t('news.catPolicy'), value: 'policy' },
  { label: t('news.catTech'), value: 'tech' },
  { label: t('news.catMarket'), value: 'market' },
  { label: t('news.catReport'), value: 'report' },
  { label: t('news.catNotice'), value: 'notice' }
]);

// 获取分类标签
const getCategoryLabel = (value) => {
  const category = categories.value.find(item => item.value === value);
  return category ? category.label : value;
};

// 标签类型
const getTagType = (tag) => {
  const types = ['', 'success', 'info', 'warning', 'danger'];
  let hash = 0;
  for (let i = 0; i < tag.length; i++) {
    hash = tag.charCodeAt(i) + ((hash << 5) - hash);
  }
  return types[Math.abs(hash) % types.length];
};

// 重置表单
const resetForm = () => {
  newsForm.value = {
    title: '',
    content: '',
    source: '',
    category: '',
    tags: [],
    image: null,
    is_published: true,
    summary: '',
    is_featured: false,
    // 第 401 批：新建新闻时这两个字段是"确定的空"，提交时按空值处理
    external_url: '',
    related_pests: []
  };
  // 新建 = 后端关系必然为空，允许带 clear_related_pests（编辑时由 loadNewsDetail 覆盖）
  relatedPestsKnown.value = true;
  editingNews.value = null;
  if (newsFormRef.value) {
    newsFormRef.value.resetFields();
  }
};

// 显示添加新闻对话框
const goToAddNews = () => {
  // 重置表单
  resetForm();
  // 设置编辑状态
  editingNews.value = null;
  // 第 401 批：打开弹窗时再加载病害选项（管理员才需要，且只加载一次）
  loadPestOptions();
  // 显示对话框
  showAddDialog.value = true;
};

// 编辑新闻
const editNews = async (news) => {
  // 第 401 批：与管理页一致，打开编辑弹窗前按需拉一次病害选项
  loadPestOptions();
  try {
    await loadNewsDetail(news.id);
  } catch (error) {
    console.error('加载新闻详情失败:', error);
    ElMessage.error(t('news.loadDetailFailed'));
  }
};

// 格式化日期
const formatDate = (dateString) => {
  if (!dateString) return '';
  const date = new Date(dateString);
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
};

// 处理搜索
const handleSearch = () => {
  currentPage.value = 1;
  fetchNews();
};

// 处理筛选条件变化
const handleFilterChange = () => {
  currentPage.value = 1;
  fetchNews();
};

/**
 * 第 399 批 · P0-2：热门标签聚合
 * 标签集合由后端按真实数据聚合，前端不硬编码。接口还没上线 / 请求失败时
 * 静默降级为空标签条，列表本身不受影响（不能因为筛选辅助功能挂掉整页）。
 */
const loadHotTags = async () => {
  try {
    const data = await fetchNewsTags();
    hotTags.value = data.tags;
  } catch (error) {
    console.warn('获取热门标签失败:', error);
    hotTags.value = [];
  }
};

// 第 399 批：点选 / 取消一个热门标签；多标签按 AND 语义交给后端（逗号分隔）
const toggleTag = (name) => {
  selectedTags.value = selectedTags.value.includes(name)
    ? selectedTags.value.filter((tag) => tag !== name)
    : [...selectedTags.value, name];
  currentPage.value = 1;
  fetchNews();
};

// 第 399 批：一键清除标签筛选
const clearTags = () => {
  if (selectedTags.value.length === 0) return;
  selectedTags.value = [];
  currentPage.value = 1;
  fetchNews();
};

// 处理每页条数变化
const handleSizeChange = (val) => {
  pageSize.value = val;
  fetchNews();
};

// 处理当前页码变化
const handleCurrentChange = (val) => {
  currentPage.value = val;
  fetchNews();
};

// 加载新闻详情
const loadNewsDetail = async (id) => {
  try {
    detailLoading.value = true;
    // 注意：vite.config.ts 中已经配置了 /api 代理，所以这里不需要再加 /api
    const url = `/news/${id}/`;

    const response = await axios.get(url, {
      headers: {
        'Content-Type': 'application/json'
      }
    });

    const data = response.data;

    if (!data) {
      throw new Error(t('news.emptyData'));
    }

    // 处理标签数据
    // 后端 tags 是"逗号分隔的字符串"（见 NewsSerializer 的 tags 字段）。
    // 原来只有 Array.isArray 时才赋值，字符串形态会被丢成 []，
    // 保存时再把空数组拼成空字符串发回去 → **已有标签被静默清空**。
    let tags = [];
    if (Array.isArray(data.tags)) {
      tags = data.tags;
    } else if (typeof data.tags === 'string' && data.tags.trim()) {
      tags = data.tags.split(',').map((item) => item.trim()).filter(Boolean);
    } else if (data.tag) {
      tags = [data.tag];
    }

    // 处理图片URL
    const imageUrl = data.image || data.image_url;

    // 第 401 批：关联病害回填
    // 详情接口读的是 id 数组（related_pests）；若后端只给了 related_pest_details，
    // 就从明细里取 id 兜底。两者都没有说明是老后端 —— known=false，提交时不动这个字段。
    relatedPestsKnown.value = Array.isArray(data.related_pests)
      || Array.isArray(data.related_pest_details);
    const relatedPestIds = Array.isArray(data.related_pests)
      ? toPestIdArray(data.related_pests)
      : toPestIdArray(relatedPestsOf(data).map((pest) => pest?.id));

    // 更新表单数据
    newsForm.value = {
      ...data,
      id: data.id || null,
      title: data.title || '',
      content: data.content || '',
      source: data.source || '',
      category: data.category || '',
      tags: tags,
      image: null, // 重置为null，避免使用缓存的File对象
      image_url: imageUrl, // 确保image_url被正确设置
      image_preview: imageUrl ? getFullImageUrl(imageUrl) : null,  // 添加图片预览URL
      is_published: data.is_published || false,
      // 第 399 批：后端刚上线这两个字段时，老数据 / 老接口返回里可能没有，
      // 显式给默认值，表单就不会出现 undefined（el-switch 会当成未开启）
      summary: data.summary || '',
      is_featured: !!data.is_featured,
      // 第 401 批：原文链接 / 关联病害（关联 id 用于多选回显）
      external_url: data.external_url || '',
      related_pests: relatedPestIds
    };

    // 标记"正在编辑哪条新闻"，否则弹窗标题会显示成「添加新闻」
    editingNews.value = data;
    showAddDialog.value = true;
    return data;
  } catch (error) {
    console.error('加载新闻详情失败:', error);
    let errorMessage = t('news.loadDetailFailed');

    if (error.response) {
      // 服务器返回了错误响应
      if (error.response.status === 404) {
        errorMessage = t('news.notFound');
      } else if (error.response.status === 403) {
        errorMessage = t('news.forbidden');
      } else if (error.response.data && error.response.data.detail) {
        errorMessage = error.response.data.detail;
      }
    } else if (error.request) {
      // 请求已发出但没有收到响应
      errorMessage = t('msg.cannotConnect');
    }

    ElMessage.error(errorMessage);
    // 不自动跳转，让用户决定下一步操作
    // router.push({ name: 'news' });
    throw error; // 重新抛出错误，让调用者处理
  } finally {
    detailLoading.value = false;
  }
};

// 获取新闻列表
const fetchNews = async () => {
  // 第 380 批：发请求前先领序号（见 listRequestSeq 的说明）
  const requestId = ++listRequestSeq;
  try {
    listLoading.value = true;

    // 构建查询参数
    const params = {
      page: currentPage.value,
      page_size: pageSize.value,
      search: searchQuery.value,
      search_type: searchType.value,
      category: activeCategory.value,
      // 第 399 批 · P0-2：排序 / 时间范围 / 标签（多标签逗号分隔，后端按 AND 处理；
      // 空数组序列化成空串后会被下面的"移除空参数"删掉，等于不筛选）
      ordering: ordering.value,
      date_range: dateRange.value,
      tags: selectedTags.value.join(','),
      // 第 399 批 · P0-1：读者列表页固定要头条段；后端会把这 1~3 条从
      // results 与 count 里剔除，所以下方网格不会重复展示。
      featured: '1',
      is_published: publishStatus.value === 'published' ? 'true' :
                   publishStatus.value === 'unpublished' ? 'false' : ''
    };

    // 移除空参数
    Object.keys(params).forEach(key => {
      if (params[key] === '' || params[key] === null || params[key] === undefined) {
        delete params[key];
      }
    });

    // 构建查询字符串，确保没有多余的斜杠
    const queryString = new URLSearchParams(params).toString();
    // 确保URL格式正确，包含/api前缀
    const baseUrl = '/api/news'.replace(/\/+$/, '');
    // 加时间戳：管理端下架/发布后，浏览器不能继续拿"下架前"的缓存列表，
    // 否则会出现"后台已下架、前台刷新还是旧内容"的假象。
    const cacheBuster = `_t=${Date.now()}`;
    const url = queryString ? `${baseUrl}?${queryString}&${cacheBuster}` : `${baseUrl}?${cacheBuster}`;


    // 准备请求头
    const headers = {
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    };
    
    // 只有在有token时才添加Authorization头
    const token = getToken();
    if (token) {
      headers['Authorization'] = `Token ${token}`;
    }
    
    
    // 使用 fetch API 发送请求
    const response = await fetch(url, {
      method: 'GET',
      headers: headers,
      credentials: 'include',  // 确保发送cookies
      cache: 'no-store'        // 发布状态随时可能被管理员改动，禁用协商缓存
    });

    
    if (!response.ok) {
      // 第 380 批：响应体**只能读一次**。原来先 `response.json()`，解析失败再在
      // catch 里 `response.text()` —— 同一个 body 读第二遍时浏览器直接抛
      // `Failed to execute 'text' on 'Response': body stream already read`，
      // 把真正的错误信息盖掉（后端返回非 JSON 错误页时必现）。
      // 现在只读一次文本，再自己尝试解析：JSON 错误体拿到对象，非 JSON 拿到原文。
      const raw = await response.text();
      let errorData = raw;
      try {
        errorData = raw ? JSON.parse(raw) : null;
      } catch (e) {
        console.error('Failed to parse error response as JSON, keep raw text:', e);
      }
      console.error('Error response data:', errorData);
      
      const error = new Error(`HTTP error! status: ${response.status}`);
      error.response = {
        status: response.status,
        statusText: response.statusText,
        data: errorData
      };
      throw error;
    }
    
    const data = await response.json();

    // 旧请求（已被更新的筛选/翻页/搜索取代）迟到：整包丢弃 ——
    // 既不覆盖新请求的列表，也不替还在途的新请求收掉骨架屏。
    if (requestId !== listRequestSeq) {
      return data;
    }

    // 第 399 批：featured 段和 results 来自同一次请求，必须一起落状态；
    // 放在请求序号检查之后，旧请求的头条才不会盖掉新筛选的结果。
    featuredList.value = Array.isArray(data?.featured) ? data.featured : [];

    // 处理响应数据
    if (data.results) {
      newsList.value = data.results;
      total.value = data.count || data.results.length;
    } else {
      newsList.value = Array.isArray(data) ? data : [];
      total.value = Array.isArray(data) ? data.length : 0;
    }
    
    return data;
  } catch (error) {
    console.error('获取新闻列表失败:', error);
    console.error('Error details:', {
      message: error.message,
      response: error.response
    });

    // 旧请求的错误不打扰用户：不弹 toast、也不清空当前列表
    // （并发时会连弹好几个错误框，还会把新请求正在用的数据清掉）
    if (requestId !== listRequestSeq) {
      return null;
    }

    newsList.value = [];
    total.value = 0;
    // 第 399 批：列表拉失败时旧头条也不能留着，否则会出现"列表空、头条区还在"的错位画面
    featuredList.value = [];

    if (error.response) {
      if (error.response.status === 401) {
        ElMessage.error(t('msg.unauthorized'));
        // 清除认证信息（两个存储一起清）
        clearIdentity();
        router.push('/login');
      } else if (error.response.status === 403) {
        ElMessage.error(t('msg.forbidden'));
      } else if (error.response.status === 404) {
        ElMessage.error(t('msg.notFoundResource'));
      } else if (error.response.status >= 500) {
        ElMessage.error(t('msg.serverError'));
      } else {
        ElMessage.error(t('msg.requestFailedWith', { detail: error.response.statusText || error.message }));
      }
    } else {
      ElMessage.error(t('msg.networkErrorWith', { detail: error.message }));
    }
    
    // 重新抛出错误，以便调用方可以处理
    throw error;
  } finally {
    // 只有"最新请求"有权收尾：旧请求结束时新请求可能还在途，
    // 这时置 false 就会出现"页面说加载完了、其实还在转"。
    if (requestId === listRequestSeq) {
      listLoading.value = false;
    }
  }
};

// 提交新闻表单
const submitNews = async () => {
  try {
    await newsFormRef.value.validate();
  } catch {
    // 表单校验失败：Element Plus 已在对应表单项上标红，这里不再弹通用错误
    return;
  }

  submitLoading.value = true;
  try {
    // 只提交后端认识的字段，并且复用「新闻管理」页同一套组装逻辑（api/news.js）。
    //
    // 原实现把详情接口返回的字段全塞进 FormData（含 id / created_at_formatted /
    // image_url），又因为 loadNewsDetail 把 image 置成了 null，于是每次保存都会
    // 额外发出 `image=''` —— 后端按"清空封面图"处理；标签数组也会被拼成空字符串。
    // 结果：在行业动态页"编辑成功"却把封面图和标签弄丢了。
    const imageFile = newsForm.value.image instanceof File ? newsForm.value.image : null;
    const payload = {
      title: newsForm.value.title,
      content: newsForm.value.content,
      category: newsForm.value.category,
      source: newsForm.value.source,
      tags: newsForm.value.tags,
      is_published: newsForm.value.is_published,
      // 第 399 批：摘要 / 精选。本页表单没有定时发布字段，因此**不**传
      // published_at —— buildNewsFormData 对缺省的键不 append，不会误清空管理页的定时发布。
      summary: newsForm.value.summary || '',
      is_featured: !!newsForm.value.is_featured,
      // 第 401 批：原文链接（空串 = 清空）与关联病害。
      // 关联病害只在"知道后端已有值"（relatedPestsKnown）时才提交：
      // 老后端没有该字段，若照常提交空数组 + clear_related_pests=true，
      // 编辑一次就会把后端存量的关联关系误清空。
      external_url: (newsForm.value.external_url || '').trim(),
      // 只有"用户确实移除了封面"（没有新文件、也没有预览）时才要求清空，
      // 否则保持原有封面不动
      clear_image: !imageFile && !newsForm.value.image_preview,
    };

    if (relatedPestsKnown.value) {
      const relatedPestIds = toPestIdArray(newsForm.value.related_pests);
      payload.related_pests = relatedPestIds;
      // multipart 无法表达"空数组"，清空用独立开关；非空时传 false 表示"以本次列表为准"
      payload.clear_related_pests = relatedPestIds.length === 0;
    }

    const newsId = newsForm.value.id || route.params.id;

    if (newsId) {
      await updateNews(newsId, payload, imageFile);
      ElMessage.success(t('news.updatedOk'));
    } else {
      await createNews(payload, imageFile);
      ElMessage.success(t('news.createdOk'));
    }

    // 刷新新闻列表并等待完成
    await fetchNews();
    // 第 399 批：新建 / 编辑可能改变标签集合，热门标签条跟着刷新一次
    loadHotTags();

    // 关闭对话框
    showAddDialog.value = false;

    // 重置表单
    resetForm();
  } catch (error) {
    console.error('保存失败:', error);
    // 原来只读 error.response.data.detail，字段级错误（典型："已存在同标题的新闻"）
    // 会退化成没有任何信息量的「保存失败」，管理员只能靠反复试。
    // 这里复用统一文案工具，把后端返回的字段错误展示出来。
    ElMessage.error(formatNewsError(error, t('msg.savingFailedRetry')));
  } finally {
    submitLoading.value = false;
  }
};

// 删除新闻
const confirmDelete = (id) => {
  ElMessageBox.confirm(t('newsDetail.deleteConfirm'), t('msg.notice'), {
    confirmButtonText: t('msg.confirmed'),
    cancelButtonText: t('msg.cancel'),
    type: 'warning'
  }).then(async () => {
    try {
      // 注意：移除了URL开头的/api，因为baseURL已经包含了/api
      await api.delete(`news/${id}/`);
      ElMessage.success(t('msg.deleteOk'));
      fetchNews();
      // 第 399 批：删除可能让某个标签从全站消失（或计数变化），标签条一起刷新
      loadHotTags();
    } catch (error) {
      console.error('删除失败:', error);
      console.error('错误详情:', {
        message: error.message,
        response: error.response?.data,
        status: error.response?.status,
        headers: error.response?.headers
      });
      ElMessage.error(error.response?.data?.detail || t('msg.deleteFailed'));
    }
  }).catch(() => {
    // 用户取消删除
  });
};

// 图片上传前处理
const beforeUpload = (file) => {
  const isImage = file.type.startsWith('image/');
  if (!isImage) {
    ElMessage.error(t('msg.imageOnly'));
    return false;
  }
  const isLt5M = file.size / 1024 / 1024 < 5;
  if (!isLt5M) {
    ElMessage.error(t('msg.imageTooLarge5'));
    return false;
  }
  return true;
};

// 说明：原来这里有一个 getCookie('csrftoken') 辅助函数，只服务于 submitNews 里
// 手写的请求头；改为统一走 @/api/news（内部用 @/api/http，已自动附带
// Token 与 X-CSRFToken）之后它就没有调用点了，故删除。
// 注意：通过统一客户端提交还避免了"手写 multipart 请求体"带来的字段污染问题。

// 处理图片URL，确保是完整路径并添加时间戳防止缓存
const getFullImageUrl = (url) => {
  // 如果URL为空或不是字符串，返回空字符串
  if (!url || typeof url !== 'string') {
    return '';
  }

  // 移除URL中可能存在的多余斜杠
  url = url.replace(/([^:]\/)\/+/g, '$1');

  // 如果URL已经是带时间戳的，直接返回
  if (url.includes('?t=')) {
    return url;
  }

  // 统一由 @/api/http 处理基础地址（自动去掉 /api 前缀，兼容绝对地址）
  const absolute = toAbsoluteMediaUrl(url);
  if (!absolute) return '';

  // 追加时间戳，避免浏览器缓存旧图
  const separator = absolute.includes('?') ? '&' : '?';
  return `${absolute}${separator}t=${Date.now()}`;
};

// 处理图片上传
const handleUpload = (file) => {

  // 生成预览URL
  const reader = new FileReader();

  // 确保我们有文件对象
  const fileObj = file.raw || file;

  if (!fileObj) {
    console.error('无效的文件对象');
    ElMessage.error(t('news.invalidFile'));
    return false;
  }

  // 检查文件类型
  const isImage = fileObj.type.startsWith('image/');
  if (!isImage) {
    ElMessage.error(t('msg.imageOnly'));
    return false;
  }

  // 检查文件大小（5MB）
  const isLt5M = fileObj.size / 1024 / 1024 < 5;
  if (!isLt5M) {
    ElMessage.error(t('msg.imageTooLarge5'));
    return false;
  }

  // 读取文件内容
  reader.onload = (e) => {
    // 直接使用Data URL作为预览
    newsForm.value.image_preview = e.target.result;

    // 保存文件对象到表单数据
    newsForm.value.image = fileObj;


    // 如果是编辑模式，清除原始图片URL，以便在提交时更新
    if (newsForm.value.id) {
      newsForm.value.image_url = null;
    }

    // 强制更新DOM
    newsForm.value = { ...newsForm.value };
  };

  reader.onerror = (error) => {
    console.error('文件读取错误:', error);
    ElMessage.error(t('news.imageUploadFailed'));
  };

  // 开始读取文件
  reader.readAsDataURL(fileObj);

  // 返回false阻止自动上传，因为我们会在submitNews中处理上传
  return false;
};

// 删除已上传的图片
const removeImage = (e) => {
  e.stopPropagation();
  newsForm.value.image = null;
  newsForm.value.image_preview = null;
  newsForm.value.image_url = null;
  // 强制更新DOM
  newsForm.value = { ...newsForm.value };
};

// 跳转到新闻详情页
const goToNewsDetail = (id) => {
  router.push({
    name: 'news-detail',
    params: { id }
  });
};

// 初始化
onMounted(() => {
  fetchNews();
  // 第 399 批：热门标签条与列表并行加载（loadHotTags 内部已兜底，失败不影响列表）
  loadHotTags();
  // 第 402 批：进入页面时核对当前分类的订阅状态（"全部分类"时内部直接跳过）
  refreshCategorySubscription();
});

// 监听路由变化：从任何"新闻相关"的深链回到本页列表时，把弹窗收起来并刷新列表
// （第 121 批：原先这里还要处理"编辑模式/创建模式"，那两条深链现在重定向走了）
watch(() => route.name, (newVal) => {
  if (newVal === 'news') {
    showAddDialog.value = false;
    fetchNews();
  }
});

// 第 402 批：切换分类 / 登录态变化时刷新「订阅该分类」按钮的状态。
// 放在 watch 而不是 handleFilterChange 里：分类除了点按钮，还可能被其它逻辑改动，
// watch 是唯一入口；且登录态变化（例如另一个标签页登录/退出后本页状态同步）也走这里。
watch(activeCategory, () => {
  refreshCategorySubscription();
});
watch(() => Boolean(authStore.user), () => {
  refreshCategorySubscription();
});

</script>

<style scoped>
/* 第 378 批：新闻卡片骨架 —— 列宽 / 封面高度 180px / 内边距 / 圆角 / 阴影都对齐真实 .news-card，
   骨架换成真实列表时不会明显跳动 */
.news-skeleton {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 22px;
  /* 与 .news-list 的 margin-top、.news-grid 的 margin-bottom 保持一致 */
  margin: 30px 0 20px;
}

.news-skeleton .skeleton-card {
  display: flex;
  flex-direction: column;
  /* 真实卡片（1440 宽、4 列）实测 546px 高；锁定同高，加载完成时整页不跳动 */
  min-height: 546px;
  overflow: hidden;
  background: var(--surface, #fff);
  border: 1px solid var(--border, #ebeef5);
  border-radius: var(--radius-lg, 12px);
  box-shadow: var(--shadow-sm, 0 2px 12px rgba(0, 0, 0, 0.05));
}

/* 真实卡片是 el-card__body(20px) + .news-content(20px) 两层内边距，
   骨架合并成一层 40px，封面图位置/宽度与真实卡片一致 */
.news-skeleton .skeleton-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 40px;
}

.news-skeleton .skeleton-cover {
  width: 100%;
  height: 180px; /* 真实 .news-image 固定 180px 高 */
  margin-bottom: 16px;
  border-radius: 4px;
  flex: none;
}

.news-skeleton .skeleton-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.news-container {
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px;
  background-color: #f5f7fa;
  min-height: calc(100vh - 60px);
}

.news-header {
  position: relative;
  text-align: match-parent;
  -webkit-text-align: match-parent;
  padding: 20px;
  background: #fff;
  border-radius: 4px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header-content h1 {
  font-size: 2.2rem;
  color: #2c3e50;
  margin: 0 0 10px;
  display: flex;
  align-items: center;
  gap: 12px;
  font-weight: 600;
}

.header-desc {
  color: #606266;
  font-size: 1.1rem;
  margin: 10px 0 0;
  line-height: 1.6;
}

.add-news-btn {
  margin-top: 20px;
  padding: 10px 24px;
  font-size: 1rem;
  font-weight: 500;
  letter-spacing: 0.5px;
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.3);
}

.filter-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 15px;
  background: #fff;
  padding: 18px 24px;
  border-radius: 12px;
  box-shadow: 0 2px 16px rgba(0, 0, 0, 0.05);
  border: 1px solid #ebeef5;
}

.search-box {
  min-width: 280px;
  flex: 0 1 auto;
}

:deep(.el-radio-group) {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-right: 10px;
}

:deep(.el-radio-button__inner) {
  border-radius: 20px !important;
  padding: 8px 18px;
  transition: all 0.3s;
  font-weight: 500;
  border: 1px solid #dcdfe6;
}

:deep(.el-radio-button__orig-radio:checked + .el-radio-button__inner) {
  background: var(--el-color-primary);
  border-color: var(--el-color-primary);
  box-shadow: 0 2px 10px var(--el-color-primary-light-5);
  color: #fff;
}

/* 头部操作按钮 */
.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-left: auto;
}

.home-button {
  margin-left: 15px;
  margin-right: 20px;
  transition: all 0.3s ease;
  background-color: var(--brand-600, #2a7f53);
  border: none;
  padding: 8px 15px;
  border-radius: 4px;
  color: white;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 6px;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
}

.home-button i {
  font-size: 16px;
}

.home-button:hover {
  background-color: var(--el-color-primary-light-3);
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

/* 新闻列表 */
.news-list {
  margin-top: 30px;
}

.news-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 24px;
  margin-bottom: 20px;
}

.news-card {
  cursor: pointer;
  transition: all 0.3s ease;
  height: 100%;
  display: flex;
  flex-direction: column;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);
  -webkit-transition: all 0.3s ease;
  transition: all 0.3s ease;
}

.news-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 6px 18px 0 rgba(0, 0, 0, 0.1);
}

.news-content {
  display: flex;
  flex-direction: column;
  flex: 1;
  padding: 20px;
}

.news-image {
  width: 100%;
  height: 180px;
  overflow: hidden;
  position: relative;
  border-radius: 4px 4px 0 0;
  margin-bottom: 16px;
}

.news-image .el-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s;
}

.news-card:hover .news-image .el-image {
  transform: scale(1.05);
}

.news-category {
  position: absolute;
  top: 10px;
  right: 10px;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.news-details {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.news-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 12px 0;
  color: #303133;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.4;
}

.news-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  color: #909399;
  font-size: 13px;
  margin-bottom: 12px;
}

.news-meta span {
  display: flex;
  align-items: center;
  gap: 4px;
}

.news-meta i {
  font-size: 14px;
}

/* 第 33 批：图片上传改用主题里的 .upload-tile 瓦片
   （原来的 .image-uploader / .image-preview-wrapper / .image-actions 一整套
   自定义样式已随旧弹窗一起删除）。这里只负责抹掉 el-upload 自带的 drag 外壳，
   让瓦片自己撑满、不要出现双层虚线边框。 */
.tile-uploader {
  width: 100%;
}

.tile-uploader :deep(.el-upload),
.tile-uploader :deep(.el-upload-dragger) {
  width: 100%;
  padding: 0;
  border: none;
  background: transparent;
}

.tile-uploader :deep(.el-upload-dragger.is-dragover) {
  border: none;
  background: transparent;
}

.news-summary {
  color: #606266;
  font-size: 14px;
  line-height: 1.8;
  margin-bottom: 16px;
  flex: 1;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
}

.news-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px dashed #e4e7ed;
}

.news-tags {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 5px;
}

.news-actions {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-left: auto;
}

.news-actions .el-button {
  padding: 4px 8px;
  font-size: 12px;
  color: #606266;
  transition: all 0.3s;
}

.news-actions .el-button:hover {
  color: var(--el-color-primary);
  background-color: var(--el-color-primary-light-9);
}

.news-actions .el-button + .el-button {
  margin-left: 0;
}

.read-more {
  color: var(--el-color-primary);
  font-size: 13px;
  font-weight: 500;
  transition: all 0.3s;
}

.read-more:hover {
  color: var(--el-color-primary-light-3);
}

.read-more i {
  transition: transform 0.3s;
}

.read-more:hover i {
  transform: translateX(3px);
}

.news-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.1);
  border-color: #e4e7ed;
}

.news-uploader {
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #f5f7fa;
  -webkit-transition: border-color 0.3s;
  transition: border-color 0.3s;
  border: 1px dashed #d9d9d9;
  border-radius: 8px;
  width: 100%;
  height: 180px;
  cursor: pointer;
  -webkit-appearance: none;
  appearance: none;
  -webkit-text-size-adjust: 100%;
  -ms-text-size-adjust: 100%;
  -moz-text-size-adjust: 100%;
  text-size-adjust: 100%;
}

.news-uploader:hover {
  border-color: var(--brand-400, #5fb088);
}

.news-uploader-icon {
  font-size: 36px;
  color: #8c939b;
  transition: color 0.3s;
}

.news-uploader:hover .news-uploader-icon {
  color: var(--brand-600, #2a7f53);
}

.news-uploader-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s;
}

.news-uploader-img:hover {
  transform: scale(1.05);
}

/* 弹窗样式 */
:deep(.el-dialog) {
  border-radius: 12px;
  max-width: 700px;
}

:deep(.el-dialog__header) {
  padding: 20px 24px;
  border-bottom: 1px solid #f0f0f0;
  margin-right: 0;
}

:deep(.el-dialog__title) {
  font-size: 1.2rem;
  font-weight: 600;
  color: #303133;
}

:deep(.el-dialog__body) {
  padding: 24px;
}

/* 响应式布局 */
@media (max-width: 1200px) {
  .news-grid {
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 20px;
  }
}

@media (max-width: 992px) {
  .news-grid {
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
    gap: 16px;
  }

  .board-latest {
    display: none;
  }
}

@media (max-width: 768px) {
  .news-container {
    padding: 15px;
  }

  .news-header {
    padding: 30px 15px;
  }

  .header-content h1 {
    font-size: 1.8rem;
  }

  .news-categories {
    flex-direction: column;
    align-items: stretch;
    padding: 15px;
  }

  .search-box {
    width: 100%;
    margin-top: 10px;
  }

  :deep(.el-radio-group) {
    justify-content: center;
    margin-bottom: 10px;
  }

  .news-grid {
    grid-template-columns: 1fr;
    gap: 20px;
  }

  .news-uploader {
    height: 180px;
  }
}

@media (max-width: 480px) {
  .header-content h1 {
    font-size: 1.6rem;
  }

  .header-desc {
    font-size: 1rem;
  }

  :deep(.el-radio-button__inner) {
    padding: 6px 14px;
    font-size: 13px;
  }
}

/* ================= 现代化覆写（设计变量见 assets/theme.css） ================= */
.news-container {
  width: 100%;
  max-width: 1500px;
  margin: 0 auto;
  padding: 8px 24px 48px;
  box-sizing: border-box;
}

/* 顶部标题区 */
.news-header {
  padding: 34px 32px;
  margin-bottom: 22px;
  border-radius: var(--radius-xl);
  background: var(--gradient-brand-soft);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
}

.header-content h1,
.news-header h1 {
  font-size: 28px;
  font-weight: 800;
  color: var(--brand-800);
  letter-spacing: 0.5px;
}

.header-desc {
  margin-top: 8px;
  font-size: 14px;
  color: var(--ink-500);
}

/* 筛选栏 */
.filter-container {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 16px 20px;
  margin-bottom: 24px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-xs);
}

.filter-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 8px;
}

.search-box input {
  border-radius: var(--radius-pill);
  border: 1px solid var(--border-strong);
  padding: 9px 18px;
  font-size: 14px;
  transition: border-color var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}

.search-box input:focus {
  outline: none;
  border-color: var(--brand-500);
  box-shadow: var(--shadow-focus);
}

.add-news-btn {
  margin-left: auto;
  border-radius: var(--radius-pill);
  background: var(--gradient-brand);
  border: none;
  color: #fff;
  padding: 10px 22px;
  font-weight: 600;
  box-shadow: 0 8px 18px rgba(31, 99, 67, 0.2);
  cursor: pointer;
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}

.add-news-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 12px 24px rgba(31, 99, 67, 0.26);
}

/* 新闻网格 */
.news-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 22px;
}

.news-card {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}

.news-card:hover {
  transform: translateY(-6px);
  box-shadow: var(--shadow-lg);
}

.news-image {
  position: relative;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background: var(--ink-50);
}

.news-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.45s var(--ease);
}

.news-card:hover .news-image img {
  transform: scale(1.06);
}

.no-image {
  display: grid;
  place-items: center;
  width: 100%;
  height: 100%;
  color: var(--ink-300);
  font-size: 34px;
  background: var(--ink-50);
}

.news-content {
  display: flex;
  flex-direction: column;
  flex: 1;
  padding: 20px;
}

.news-title {
  margin: 0 0 10px;
  font-size: 17px;
  font-weight: 700;
  line-height: 1.5;
  color: var(--ink-800);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.news-summary {
  margin: 0 0 14px;
  font-size: 13.5px;
  line-height: 1.75;
  color: var(--ink-500);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.news-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-top: auto;
  font-size: 12.5px;
  color: var(--ink-400);
}

.news-category {
  padding: 3px 12px;
  border-radius: var(--radius-pill);
  background: var(--brand-50);
  color: var(--brand-700);
  font-weight: 600;
}

.news-source,
.news-views {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.news-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 14px;
}

.news-tags span,
.news-tags .el-tag {
  border-radius: var(--radius-pill);
}

.news-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 14px;
  margin-top: 14px;
  border-top: 1px solid var(--border);
}

.read-more {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--brand-700);
  font-size: 13.5px;
  font-weight: 600;
  text-decoration: none;
  transition: gap var(--dur) var(--ease);
}

.read-more:hover {
  gap: 10px;
}

.news-actions {
  display: flex;
  gap: 8px;
}

/* 分页 */
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 28px;
}

/* 表单弹窗（第 33 批：弹窗外壳、分段与底部操作条已抽到 theme.css 的
   .form-dialog / .form-section / .form-dialog-footer，这里只留图片占位） */
.image-slot {
  border-radius: var(--radius);
  border: 1px dashed var(--border-strong);
  background: var(--surface-muted);
}

@media (max-width: 768px) {
  .news-container {
    padding: 0 16px 32px;
  }

  .news-header {
    padding: 24px 20px;
  }

  .news-grid {
    grid-template-columns: 1fr;
  }

  .add-news-btn {
    margin-left: 0;
    width: 100%;
  }
}

/* ================= 第 399 批：头条精选 / 筛选栏 / 卡片交互（P0-1、P0-2、P0-4） ================= */

/* ---- 筛选栏：排序 / 时间范围 / 热门标签条 ---- */
.filter-select {
  width: 128px;
}

/* 原来搜索框是内联 style="width:300px"，移动端没法用媒体查询覆盖；
   改由 class 控制，窄屏下 100% */
.news-search-input {
  width: 300px;
}

/* 热门标签条独占第二行（flex-basis:100%），不把分类按钮与搜索框挤成多行 */
.hot-tags-bar {
  flex-basis: 100%;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding-top: 12px;
  border-top: 1px dashed var(--border);
}

.hot-tags-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-500);
  white-space: nowrap;
}

.hot-tags-list {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
}

.hot-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-pill);
  background: var(--surface);
  color: var(--ink-600);
  font-size: 12.5px;
  line-height: 1.6;
  cursor: pointer;
  transition: color var(--dur) var(--ease), border-color var(--dur) var(--ease),
    background var(--dur) var(--ease);
}

.hot-tag:hover {
  border-color: var(--brand-400);
  color: var(--brand-700);
}

.hot-tag.is-active {
  border-color: var(--brand-600);
  background: var(--brand-600);
  color: #fff;
}

.hot-tag-count {
  font-size: 11px;
  opacity: 0.75;
}

.hot-tags-empty {
  font-size: 12.5px;
  color: var(--ink-400);
}

.clear-tags-btn {
  margin-left: auto;
  color: var(--brand-700);
}

/* ---- 头条精选区：1 条通栏，2~3 条两列；<=900px 纵向堆叠 ---- */
.featured-section {
  margin-bottom: 26px;
  padding: 20px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--gradient-brand-soft);
  box-shadow: var(--shadow-sm);
}

.featured-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.featured-head h2 {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 19px;
  font-weight: 800;
  color: var(--brand-800);
}

.featured-head h2 i {
  color: var(--brand-500);
}

.featured-head-count {
  min-width: 22px;
  padding: 0 7px;
  border-radius: var(--radius-pill);
  background: var(--brand-600);
  color: #fff;
  font-size: 12px;
  line-height: 20px;
  text-align: center;
}

.featured-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.featured-grid.is-single {
  grid-template-columns: 1fr;
}

/* 只有 1 条头条时卡片通栏、封面列很宽：若仍按"填满卡片高度"拉伸，
   图会被裁成 2.4:1 的横幅。这里用 16:9 定住图片比例并垂直居中。 */
.featured-grid.is-single .featured-cover {
  flex: 0 0 48%;
  aspect-ratio: 16 / 9;
  align-self: center;
}

/* 横向大卡片：左图 16:9 + 右侧标题/摘要/meta */
.featured-card {
  display: flex;
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: var(--shadow-xs);
  cursor: pointer;
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}

.featured-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-md);
}

.featured-cover {
  position: relative;
  flex: 0 0 44%;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background: var(--ink-50);
}

.featured-cover-img,
.featured-cover .el-image {
  display: block;
  width: 100%;
  height: 100%;
}

.featured-cover-img :deep(img) {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.45s var(--ease);
}

.featured-card:hover .featured-cover-img :deep(img) {
  transform: scale(1.04);
}

.featured-cover .news-category {
  position: absolute;
  top: 10px;
  right: 10px;
}

.featured-flag {
  position: absolute;
  top: 10px;
  left: 10px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  background: rgba(31, 99, 67, 0.92);
  color: #fff;
  font-size: 11.5px;
  font-weight: 600;
}

.featured-cover .no-image {
  /* aspect-ratio 算出来的高度对子元素 height:100% 不一定可解析，
     用绝对定位保证占位图撑满整个封面框并居中 */
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 13px;
}

.featured-body {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  padding: 16px 18px;
}

.featured-title {
  margin: 0 0 8px;
  font-size: 16.5px;
  font-weight: 700;
  line-height: 1.45;
  color: var(--ink-800);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.featured-summary {
  margin: 0 0 12px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--ink-500);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.featured-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-top: auto;
  font-size: 12px;
  color: var(--ink-400);
}

.featured-meta span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.featured-read-more {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--brand-700);
}

/* ---- 主卡片：封面精选标记 + 操作区交互（P0-4） ---- */
.news-featured-flag {
  position: absolute;
  top: 10px;
  left: 10px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  background: rgba(31, 99, 67, 0.92);
  color: #fff;
  font-size: 11.5px;
  font-weight: 600;
  pointer-events: none;
}

/* 操作按钮默认隐藏，hover / focus-within 出现；管理员身份始终可见（.is-admin）。
   用 opacity 而不是 display:none —— 保留占位，悬停时卡片高度不跳动。 */
.news-actions {
  opacity: 0;
  transform: translateY(2px);
  transition: opacity var(--dur) var(--ease), transform var(--dur) var(--ease);
}

.news-card:hover .news-actions,
.news-card:focus-within .news-actions,
.news-actions.is-admin {
  opacity: 1;
  transform: none;
}

/* 触屏设备没有 hover，操作区必须常显，否则按钮永远点不到 */
@media (hover: none) {
  .news-actions {
    opacity: 1;
    transform: none;
  }
}

/* ---- 响应式：窄屏不横向溢出 ---- */
@media (max-width: 900px) {
  .featured-grid,
  .featured-grid.is-single {
    grid-template-columns: 1fr;
  }

  .featured-card {
    flex-direction: column;
  }

  .featured-cover {
    flex: none;
    width: 100%;
  }
}

@media (max-width: 768px) {
  .filter-container {
    align-items: stretch;
  }

  .filter-left {
    width: 100%;
  }

  .filter-select {
    flex: 1 1 120px;
    width: auto;
    min-width: 0;
  }

  .search-box {
    width: 100%;
  }

  .news-search-input {
    width: 100%;
  }

  /* 标签条在手机上是横向滚动条：不换行撑高、也不撑破页面
     ------------------------------------------------------------------
     第 399 批实测（375px + 9 个真实标签）：只写 width:100% + overflow-x:auto
     还不够 —— `.hot-tags-bar` 作为 `.filter-container` 的 flex item，默认
     `min-width:auto`（= 内容最小宽度），9 个 chip 的 nowrap 总宽把它撑到 524px，
     子元素 width:100% 跟着变成 524，整页出现 187px 横向滚动条。
     这里给父级补 min-width:0/max-width:100% 让它能真正收缩，子级再 max-width:100%
     兜底，溢出才会被 `overflow-x:auto` 收进标签条内部而不是整页。 */
  .hot-tags-bar {
    align-items: flex-start;
    min-width: 0;
    max-width: 100%;
  }

  .hot-tags-list {
    flex-wrap: nowrap;
    width: 100%;
    max-width: 100%;
    min-width: 0;
    overflow-x: auto;
    padding-bottom: 4px;
    -webkit-overflow-scrolling: touch;
  }

  .hot-tag {
    flex: 0 0 auto;
  }

  .clear-tags-btn {
    margin-left: 0;
  }

  /* 375px：total / sizes / jumper 全排开必然横向溢出，这里只留上一页/页码/下一页，
     并允许换行（上一页 + 多个页码 + 下一页在 375px 仍可能换行） */
  .pagination {
    flex-wrap: wrap;
  }

  .pagination :deep(.el-pagination) {
    flex-wrap: wrap;
    justify-content: center;
    row-gap: 8px;
  }

  .pagination :deep(.el-pagination__sizes),
  .pagination :deep(.el-pagination__jump) {
    display: none;
  }

  .news-actions {
    opacity: 1;
    transform: none;
  }
}

@media (max-width: 480px) {
  .featured-section {
    padding: 14px;
  }

  .featured-body {
    padding: 14px;
  }

  .featured-title {
    font-size: 15.5px;
  }
}

/* ================= 第 401 批：官方来源 / 原文外链 / 关联病害 chip ================= */
.official-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 8px;
  border-radius: var(--radius-pill);
  background: var(--brand-100);
  color: var(--brand-700);
  font-size: 11px;
  font-weight: 700;
  line-height: 18px;
  white-space: nowrap;
}

.official-badge i {
  font-size: 10px;
}

.news-external {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--brand-700);
  font-size: 12.5px;
  font-weight: 600;
  text-decoration: none;
  white-space: nowrap;
  border-bottom: 1px dashed transparent;
  transition: color var(--dur) var(--ease), border-color var(--dur) var(--ease);
}

.news-external:hover {
  color: var(--brand-500);
  border-bottom-color: var(--brand-300);
}

/* 关联病害 chip：与标签区分开（标签是 el-tag 的彩色块，这里是描边胶囊） */
.news-pests {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 0 0 12px;
}

.featured-pests {
  margin: 10px 0 0;
}

.pest-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  max-width: 100%;
  padding: 3px 10px;
  border: 1px solid var(--brand-200);
  border-radius: var(--radius-pill);
  background: var(--brand-50);
  color: var(--brand-700);
  font-size: 12px;
  line-height: 18px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: pointer;
  transition: border-color var(--dur) var(--ease), background var(--dur) var(--ease);
}

.pest-chip:hover {
  border-color: var(--brand-400);
  background: var(--brand-100);
}

.pest-chip i {
  font-size: 11px;
}

.pest-chip-more {
  border-color: var(--border-strong);
  background: var(--surface-muted);
  color: var(--ink-500);
  cursor: default;
}

/* ================= 第 402 批：分类订阅按钮 ================= */
.subscribe-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 16px;
  border: 1px dashed var(--brand-300);
  border-radius: var(--radius-pill);
  background: var(--brand-50);
  color: var(--brand-700);
  font-family: inherit;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.4;
  white-space: nowrap;
  cursor: pointer;
  transition: border-color var(--dur) var(--ease), background var(--dur) var(--ease),
    color var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}

.subscribe-btn:hover {
  border-style: solid;
  border-color: var(--brand-400);
  background: var(--brand-100);
}

.subscribe-btn i {
  font-size: 12px;
}

/* 已订阅：实心品牌色，和「可订阅」的虚线胶囊形成明确区分 */
.subscribe-btn.is-subscribed {
  border-style: solid;
  border-color: var(--brand-600);
  background: var(--brand-600);
  color: #fff;
}

.subscribe-btn.is-subscribed:hover {
  border-color: var(--brand-700);
  background: var(--brand-700);
}

.subscribe-btn:disabled {
  opacity: 0.65;
  cursor: wait;
  transform: none;
}

@media (max-width: 768px) {
  /* 375px：筛选栏元素都允许换行；按钮文字不换行但自身可占一整行 */
  .subscribe-btn {
    flex: 0 1 auto;
  }
}
</style>
