<template>
  <div class="admin-users tinted-page">
    <!-- 第 117 批：原来的「返回」按钮已移除（本页现在在管理后台外壳里，左侧栏就是导航） -->

    <!-- 页头（沿用全站 .admin-hero：深绿实底 + 白色文字） -->
    <header class="admin-hero">
      <div class="admin-hero-main">
        <span class="admin-hero-icon"><i class="fas fa-users-gear"></i></span>
        <div>
          <h1>{{ t('adminUsers.title') }}</h1>
          <p>{{ t('adminUsers.subtitle') }}</p>
        </div>
      </div>
      <div class="admin-hero-actions">
        <!--
          第 131 批：开通编辑员账号（仅超级管理员）
          ----------------------------------------------------------------
          在这之前"新建编辑员"必须去 Django admin 建号、再回来勾模块，
          而且新建的账号还得自己想办法设密码。这里一次做完：
          建号（**无可用密码**）→ 勾模块 → 返回一次性设置密码链接。
        -->
        <el-button v-if="canCreateEditor" class="btn-on-brand" @click="openCreateEditor">
          <i class="fas fa-user-plus"></i> {{ t('adminUsers.createEditorAction') }}
        </el-button>
        <el-button plain :loading="loading" @click="reload">
          <i class="fas fa-sync-alt"></i> {{ t('adminUsers.refresh') }}
        </el-button>
      </div>
    </header>

    <!-- 概览小卡 -->
    <div class="admin-stats">
      <div class="stat-tile">
        <span class="stat-tile-icon"><i class="fas fa-users"></i></span>
        <div>
          <div class="stat-tile-value">{{ stats.total }}</div>
          <div class="stat-tile-label">{{ t('adminUsers.statTotal') }}</div>
        </div>
      </div>
      <div class="stat-tile stat-tile--processing">
        <span class="stat-tile-icon"><i class="fas fa-user-shield"></i></span>
        <div>
          <div class="stat-tile-value">{{ stats.staff }}</div>
          <div class="stat-tile-label">{{ t('adminUsers.statStaff') }}</div>
        </div>
      </div>
      <div class="stat-tile stat-tile--ok">
        <span class="stat-tile-icon"><i class="fas fa-user-tie"></i></span>
        <div>
          <div class="stat-tile-value">{{ stats.expert }}</div>
          <div class="stat-tile-label">{{ t('adminUsers.statExpert') }}</div>
        </div>
      </div>
      <div class="stat-tile stat-tile--pending">
        <span class="stat-tile-icon"><i class="fas fa-user"></i></span>
        <div>
          <div class="stat-tile-value">{{ stats.normal }}</div>
          <div class="stat-tile-label">{{ t('adminUsers.statNormal') }}</div>
        </div>
      </div>
    </div>

    <!-- 筛选 -->
    <div class="filter-bar">
      <!-- 第 88 批：两个下拉都补 @clear。
           Element Plus 的 el-select 清除时是 `emitChange(value)` → `emit('clear')`，
           而 emitChange 带 `isEqual(props.modelValue, val)` 守卫（useSelect.mjs 的
           deleteSelected / emitChange）—— 这次 change 一旦被挡掉，只挂在 @change 上的
           筛选就不会重查，列表停在原来的筛选结果里：用户看到的就是
           "选了角色只能看当前的，清不掉、看不到全部"。`clear` 是无条件发出的，
           挂它才能保证"清掉角色 → 回到全部用户"。 -->
      <el-select
        v-model="filters.role"
        :placeholder="t('adminUsers.roleFilter')"
        clearable
        style="width: 150px"
        @change="applyFilter"
        @clear="handleClear"
      >
        <el-option :label="t('adminUsers.roleAdmin')" value="ADMIN" />
        <el-option :label="t('adminUsers.roleEditor')" value="EDITOR" />
        <el-option :label="t('adminUsers.roleUser')" value="USER" />
      </el-select>
      <el-select
        v-model="filters.status"
        :placeholder="t('adminUsers.statusFilter')"
        clearable
        style="width: 150px"
        @change="applyFilter"
        @clear="handleClear"
      >
        <el-option :label="t('adminUsers.statusActive')" value="active" />
        <el-option :label="t('adminUsers.statusDisabled')" value="disabled" />
        <el-option :label="t('adminUsers.statusExpert')" value="expert" />
        <el-option :label="t('adminUsers.statusStaff')" value="staff" />
      </el-select>
      <!--
        第 144 批：账号范围（默认只看"正常"账号）
        ----------------------------------------------------------------
        在此之前已注销与注销冷静期的账号在控制台里**完全看不到** ——
        端点其实一直支持（`?include_deleted=true` / `?pending_deletion=true`，第 95/101 批），
        只是界面没有开关，要看只能直连接口。这三档互斥，所以做成一个下拉而不是两个勾选框。
      -->
      <el-select
        v-model="filters.scope"
        :placeholder="t('adminUsers.scopeFilter')"
        style="width: 168px"
        @change="applyFilter"
      >
        <el-option :label="t('adminUsers.scopeNormal')" value="" />
        <el-option :label="t('adminUsers.scopeIncludeDeleted')" value="include_deleted" />
        <el-option :label="t('adminUsers.scopePendingDeletion')" value="pending_deletion" />
      </el-select>
      <el-input
        v-model="filters.search"
        :placeholder="t('adminUsers.searchPlaceholder')"
        clearable
        style="width: 260px"
        @clear="applyFilter"
        @keyup.enter="applyFilter"
      >
        <template #prefix><i class="fas fa-search"></i></template>
        <template #append>
          <el-button @click="applyFilter"><i class="fas fa-search"></i></el-button>
        </template>
      </el-input>
      <!-- 第 88 批：一键回到"全部用户"（三个筛选条件都清掉） -->
      <el-button plain :disabled="!hasFilter" @click="resetFilters">
        <i class="fas fa-rotate-left"></i> {{ t('adminUsers.resetFilters') }}
      </el-button>
      <span class="total-hint">{{ t('adminUsers.totalHint', { count: total }) }}</span>
    </div>

    <!-- 列表 -->
    <div class="panel-head list-panel-head">
      <span class="panel-icon"><i class="fas fa-address-book"></i></span>
      <h3 class="panel-title">{{ t('adminUsers.listTitle') }}</h3>
      <span class="panel-count">{{ total }}</span>
      <div class="panel-head-right">
        <!--
          第 100 批：批量操作条
          ------------------------------------------------------------------
          只在有选中行时出现 —— 平时不占位置。删除是最需要批量的操作：
          "清理一批测试账号"以前要点 N 次删除、输 N 次用户名。
        -->
        <template v-if="selectedRows.length">
          <span class="selection-hint">{{ t('adminUsers.selectedCount', { count: selectedRows.length }) }}</span>
          <el-button size="small" type="danger" plain @click="openBulkDelete">
            <i class="fas fa-trash"></i> {{ t('adminUsers.bulkDeleteAction') }}
          </el-button>
          <el-button size="small" text @click="clearSelection">{{ t('adminUsers.clearSelection') }}</el-button>
        </template>
        <span v-else class="panel-hint">{{ t('adminUsers.listHint') }}</span>
      </div>
    </div>

    <!--
      ⚠️ 排序要交给**后端**（`sortable="custom"` + `@sort-change`），不要用 el-table 自带的
      前端排序：表格里只有当前这一页的 10 行，前端排序会让人以为"全库最大的在前"，
      实际只是"这 10 条里最大的在前" —— 属于会误导决策的那种错。
    -->
    <el-table
      ref="userTableRef"
      v-loading="loading"
      :data="items"
      style="width: 100%"
      row-key="id"
      @selection-change="onSelectionChange"
      @sort-change="onSortChange"
    >
      <el-table-column type="selection" width="46" :selectable="isRowSelectable" />
      <el-table-column :label="t('adminUsers.colUser')" min-width="240" prop="username" sortable="custom">
        <template #default="{ row }">
          <div class="user-cell">
            <el-avatar :size="34" :src="row.avatar || undefined">
              {{ row.username?.[0]?.toUpperCase() }}
            </el-avatar>
            <div class="user-cell-text">
              <span class="user-name">{{ row.username }}</span>
              <span class="user-email">{{ row.email || t('adminUsers.noEmail') }}</span>
              <!--
                第 128 批：编辑员要能一眼看出"他管哪几块" ——
                否则列表里只剩一个"信息编辑员"标签，还得点开弹窗才知道细节。
              -->
              <span v-if="row.content_modules_display?.length" class="user-modules">
                <i class="fas fa-shield-halved"></i>
                {{ row.content_modules_display.join('、') }}
              </span>
            </div>
          </div>
        </template>
      </el-table-column>

      <el-table-column :label="t('adminUsers.colRole')" width="120">
        <template #default="{ row }">
          <el-tag size="small" effect="plain" :type="roleTagType(row)">{{ roleLabel(row) }}</el-tag>
        </template>
      </el-table-column>

      <el-table-column :label="t('adminUsers.colStatus')" width="200">
        <template #default="{ row }">
          <el-tag size="small" :type="statusTagType(row)" effect="light">{{ statusLabel(row) }}</el-tag>
          <el-tag v-if="row.is_expert" size="small" type="success" effect="dark" class="expert-tag">
            <i class="fas fa-user-tie"></i> {{ row.expert_title || t('adminUsers.statusExpert') }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column :label="t('adminUsers.colActivity')" width="190" prop="detections" sortable="custom">
        <template #default="{ row }">
          <span class="activity-text">
            {{ t('adminUsers.activitySummary', {
              posts: row.post_count, comments: row.comment_count, detections: row.detection_count,
            }) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column :label="t('adminUsers.colJoined')" width="160" prop="date_joined" sortable="custom">
        <template #default="{ row }">{{ formatTime(row.date_joined, 'YYYY-MM-DD HH:mm') }}</template>
      </el-table-column>

      <el-table-column :label="t('adminUsers.colLastLogin')" width="160" prop="last_login" sortable="custom">
        <template #default="{ row }">
          <span v-if="row.last_login">{{ formatTime(row.last_login, 'YYYY-MM-DD HH:mm') }}</span>
          <span v-else class="muted">{{ t('adminUsers.neverLoggedIn') }}</span>
        </template>
      </el-table-column>

      <el-table-column :label="t('adminUsers.colActions')" width="356" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="openDetail(row)">
            {{ t('adminUsers.detailAction') }}
          </el-button>
          <el-button v-if="!row.is_expert" size="small" type="success" link @click="openGrant(row)">
            {{ t('adminUsers.grantAction') }}
          </el-button>
          <el-button v-else size="small" type="danger" link @click="doRevoke(row)">
            {{ t('adminUsers.revokeAction') }}
          </el-button>
          <!-- 第 120 批：签发一次性密码重置链接（账号没绑邮箱时，这是唯一走得通的路） -->
          <el-button
            size="small"
            type="warning"
            link
            :disabled="!canResetLink(row)"
            :title="resetLinkBlockedReason(row)"
            @click="openResetLink(row)"
          >
            {{ t('adminUsers.resetLinkAction') }}
          </el-button>
          <!-- 第 95 批：删除用户（软删除）。护栏在后端，这里只负责"别让人误点"。 -->
          <el-button
            size="small"
            type="danger"
            link
            :disabled="!canDelete(row)"
            :title="deleteBlockedReason(row)"
            @click="openDelete(row)"
          >
            {{ t('adminUsers.deleteAction') }}
          </el-button>
          <!--
            第 137 批：停用 / 恢复账号（可逆，和"删除"不是一回事）
            ----------------------------------------------------------------
            在这之前页面有「已禁用」筛选和状态标签，却**没有入口能停用账号** ——
            状态只能来自"用户自助注销"或"管理员删除"，而这两类都被默认列表排除，
            于是那个筛选永远筛不出东西。这里补上按钮，并按行状态显示"停用/恢复"。
          -->
          <el-button
            size="small"
            :type="row.is_active ? 'warning' : 'success'"
            link
            :disabled="!canToggleStatus(row)"
            :title="statusBlockedReason(row)"
            @click="toggleStatus(row)"
          >
            {{ row.is_active ? t('adminUsers.statusDisableAction') : t('adminUsers.statusEnableAction') }}
          </el-button>
          <!--
            第 127 批：改角色（信息编辑员 ↔ 普通用户）。
            只在"当前登录者是超级管理员"且"这一行是普通账号"时出现 ——
            ADMIN 账号、staff/超管账号都不在这里改（后端也会拒，见 AdminUserRoleView）。
          -->
          <el-button
            v-if="canChangeRole(row)"
            size="small"
            type="info"
            link
            :title="t('adminUsers.roleActionHint')"
            @click="openRoleDialog(row)"
          >
            {{ t('adminUsers.roleAction') }}
          </el-button>
        </template>
      </el-table-column>

      <template #empty>
        <div class="table-empty">
          <i class="fas fa-inbox"></i>
          <p>{{ t('adminUsers.empty') }}</p>
        </div>
      </template>
    </el-table>

    <div class="pagination-wrap">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        :total="total"
        background
        @size-change="handleSizeChange"
        @current-change="loadList"
      />
    </div>

    <!-- 用户详情 -->
    <el-dialog v-model="detailVisible" :title="t('adminUsers.detailTitle')" width="640px" top="8vh">
      <el-skeleton v-if="detailLoading" :rows="6" animated />
      <template v-else-if="detail">
        <div class="detail-head">
          <el-avatar :size="52" :src="detail.avatar || undefined">
            {{ detail.username?.[0]?.toUpperCase() }}
          </el-avatar>
          <div>
            <strong class="detail-name">{{ detail.username }}</strong>
            <div class="detail-tags">
              <el-tag size="small" effect="plain" :type="roleTagType(detail)">{{ roleLabel(detail) }}</el-tag>
              <el-tag size="small" :type="statusTagType(detail)" effect="light">{{ statusLabel(detail) }}</el-tag>
              <el-tag v-if="detail.is_expert" size="small" type="success" effect="dark">
                <i class="fas fa-user-tie"></i> {{ detail.expert_title || t('adminUsers.statusExpert') }}
              </el-tag>
            </div>
          </div>
        </div>

        <h4 class="detail-section">{{ t('adminUsers.basicInfo') }}</h4>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="t('adminUsers.fieldId')">{{ detail.id }}</el-descriptions-item>
          <el-descriptions-item :label="t('adminUsers.fieldUsername')">{{ detail.username }}</el-descriptions-item>
          <el-descriptions-item :label="t('adminUsers.fieldEmail')">{{ detail.email || t('adminUsers.noEmail') }}</el-descriptions-item>
          <el-descriptions-item :label="t('adminUsers.fieldName')">{{ fullName(detail) || '—' }}</el-descriptions-item>
          <el-descriptions-item :label="t('adminUsers.fieldPoints')">{{ detail.points }}</el-descriptions-item>
          <el-descriptions-item :label="t('adminUsers.fieldJoined')">{{ formatTime(detail.date_joined, 'YYYY-MM-DD HH:mm') }}</el-descriptions-item>
          <el-descriptions-item :label="t('adminUsers.fieldLastLogin')" :span="2">
            {{ detail.last_login ? formatTime(detail.last_login, 'YYYY-MM-DD HH:mm') : t('adminUsers.neverLoggedIn') }}
          </el-descriptions-item>
        </el-descriptions>

        <h4 class="detail-section">{{ t('adminUsers.expertInfo') }}</h4>
        <p v-if="!detail.is_expert" class="muted">{{ t('adminUsers.notExpert') }}</p>
        <el-descriptions v-else :column="2" border size="small">
          <el-descriptions-item :label="t('adminUsers.fieldExpertTitle')">
            {{ detail.expert_title || t('adminUsers.statusExpert') }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('adminUsers.fieldExpertGrantedAt')">
            {{ formatTime(detail.expert_granted_at, 'YYYY-MM-DD HH:mm') || '—' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('adminUsers.fieldExpertSpecialties')" :span="2">
            {{ detail.expert_specialties?.length ? detail.expert_specialties.join('、') : '—' }}
          </el-descriptions-item>
        </el-descriptions>

        <h4 class="detail-section">{{ t('adminUsers.activityInfo') }}</h4>
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item :label="t('adminUsers.fieldPosts')">{{ detail.post_count }}</el-descriptions-item>
          <el-descriptions-item :label="t('adminUsers.fieldComments')">{{ detail.comment_count }}</el-descriptions-item>
          <el-descriptions-item :label="t('adminUsers.fieldDetections')">{{ detail.detection_count }}</el-descriptions-item>
        </el-descriptions>
      </template>
      <template #footer>
        <el-button @click="detailVisible = false">{{ t('adminUsers.close') }}</el-button>
      </template>
    </el-dialog>

    <!-- 授予专家 -->
    <el-dialog v-model="grantVisible" :title="t('adminUsers.grantDialogTitle')" width="480px" :close-on-click-modal="false">
      <el-form label-position="top">
        <el-form-item :label="t('adminUsers.grantTarget')">
          <el-input :model-value="grantTarget?.username" disabled />
        </el-form-item>
        <el-form-item :label="t('adminUsers.grantTitleLabel')">
          <el-input v-model="grantForm.title" maxlength="80" :placeholder="t('adminUsers.grantPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('adminUsers.grantSpecialtiesLabel')">
          <el-input
            v-model="grantForm.specialties"
            maxlength="200"
            :placeholder="t('adminUsers.grantSpecialtiesPlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="grantVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="granting" @click="submitGrant">{{ t('adminUsers.grantSubmit') }}</el-button>
      </template>
    </el-dialog>

    <!--
      签发一次性密码重置链接（第 120 批）
      ------------------------------------------------------------------
      为什么是"链接"而不是"直接把密码改成 xxx"：后者等于管理员知道了对方的口令，
      而且对方多半不会再去改它。链接是**一次性、1 小时有效、改过密码即失效**，
      管理员全程看不到新密码（后端也不返回）。
    -->
    <el-dialog
      v-model="resetLinkVisible"
      :title="t('adminUsers.resetLinkTitle')"
      width="560px"
      :close-on-click-modal="false"
    >
      <el-skeleton v-if="resetLinkLoading" :rows="3" animated />

      <template v-else>
        <el-alert v-if="resetLinkError" type="error" :closable="false" show-icon>
          {{ resetLinkError }}
        </el-alert>

        <template v-else-if="resetLinkData">
          <p class="reset-link-target">
            <i class="fas fa-user"></i>
            {{ resetLinkData.username }}
          </p>

          <el-alert type="warning" :closable="false" show-icon class="reset-link-warning">
            <p>{{ t('adminUsers.resetLinkWarning', { minutes: resetLinkData.expires_in_minutes }) }}</p>
            <p class="reset-link-sub">
              {{ resetLinkData.has_email
                ? (resetLinkData.mailed
                  ? t('adminUsers.resetLinkMailed')
                  : t('adminUsers.resetLinkMailFailed'))
                : t('adminUsers.resetLinkNoEmail') }}
            </p>
          </el-alert>

          <div class="reset-link-box">
            <input :value="resetLinkData.url" readonly class="reset-link-input" @focus="$event.target.select()" />
            <el-button type="primary" @click="copyResetLink">
              <i class="fas fa-copy"></i> {{ t('adminUsers.resetLinkCopy') }}
            </el-button>
          </div>

          <p class="reset-link-hint">
            <i class="fas fa-circle-info"></i> {{ t('adminUsers.resetLinkHowTo') }}
          </p>
        </template>
      </template>

      <template #footer>
        <el-button @click="resetLinkVisible = false">{{ t('common.close') }}</el-button>
      </template>
    </el-dialog>

    <!--
      开通编辑员账号（第 131 批）
      ------------------------------------------------------------------
      仅超级管理员可见。一次做完三件事：建号 → 勾模块 → 给出**一次性设置密码链接**。
      账号是**无可用密码**建出来的（后端 set_unusable_password），所以全程没有明文密码
      经过接口或界面；链接 1 小时有效、只能用一次，本人在 /reset-password 自己设密码。
      ⚠️ 链接**只显示这一次**：关掉弹窗就找不回来了，需要时用行内的「重置密码」重新签发。
    -->
    <el-dialog
      v-model="createEditorVisible"
      :title="t('adminUsers.createEditorTitle')"
      width="540px"
      :close-on-click-modal="false"
      @closed="resetCreateEditor"
    >
      <!-- 第一步：填账号信息 -->
      <el-form v-if="!createdEditor" label-position="top">
        <el-form-item :label="t('adminUsers.createEditorUsername')" required>
          <el-input
            v-model="createEditorForm.username"
            maxlength="20"
            :placeholder="t('adminUsers.createEditorUsernamePlaceholder')"
          />
          <p class="field-hint">{{ t('adminUsers.createEditorUsernameHint') }}</p>
        </el-form-item>
        <el-form-item :label="t('adminUsers.createEditorEmail')">
          <el-input
            v-model="createEditorForm.email"
            :placeholder="t('adminUsers.createEditorEmailPlaceholder')"
          />
          <p class="field-hint">{{ t('adminUsers.createEditorEmailHint') }}</p>
        </el-form-item>

        <el-form-item :label="t('adminUsers.roleModulesTitle')" required>
          <el-checkbox-group v-model="createEditorModules" class="role-options">
            <el-checkbox v-for="module in moduleOptions" :key="module" :value="module">
              {{ t(`contentModule.${module}`) }}
            </el-checkbox>
          </el-checkbox-group>
          <p class="field-hint">{{ t('adminUsers.roleModulesHint') }}</p>
          <!-- 第 179 批：勾了这几项 = 他能做什么（与「修改角色」对话框共用同一个组件） -->
          <EditorPermissionPreview :modules="createEditorModules" />
        </el-form-item>
      </el-form>

      <!-- 第二步：给链接（只显示这一次） -->
      <template v-else>
        <el-alert type="success" :closable="false" show-icon class="create-editor-ok">
          <!-- ⚠️ 名字在 `createdEditor.user.username` 里（接口把用户对象放在 user 下），
               写成 createdEditor.username 会渲染出「undefined」——
               浏览器端到端脚本第一次跑就是这样抓到它的。 -->
          <p>{{ t('adminUsers.createEditorOk', { name: createdEditor.user?.username || '' }) }}</p>
        </el-alert>

        <el-alert type="warning" :closable="false" show-icon class="reset-link-warning">
          <p>{{ t('adminUsers.resetLinkWarning', { minutes: createdEditor.expires_in_minutes }) }}</p>
          <p class="reset-link-sub">
            {{ createdEditor.has_email
              ? (createdEditor.mailed
                ? t('adminUsers.resetLinkMailed')
                : t('adminUsers.resetLinkMailFailed'))
              : t('adminUsers.createEditorNoEmail') }}
          </p>
        </el-alert>

        <div class="reset-link-box">
          <input :value="createdEditor.url" readonly class="reset-link-input" @focus="$event.target.select()" />
          <el-button type="primary" @click="copyCreatedEditorLink">
            <i class="fas fa-copy"></i> {{ t('adminUsers.resetLinkCopy') }}
          </el-button>
        </div>

        <p class="reset-link-hint">
          <i class="fas fa-circle-info"></i> {{ t('adminUsers.createEditorHowTo') }}
        </p>
      </template>

      <template #footer>
        <el-button @click="createEditorVisible = false">
          {{ createdEditor ? t('common.close') : t('common.cancel') }}
        </el-button>
        <el-button
          v-if="!createdEditor"
          type="primary"
          :loading="creatingEditor"
          :disabled="!createEditorForm.username.trim() || createEditorModules.length === 0"
          @click="submitCreateEditor"
        >
          {{ t('adminUsers.createEditorSubmit') }}
        </el-button>
      </template>
    </el-dialog>

    <!--
      改角色（第 127 批）
      ------------------------------------------------------------------
      只有超级管理员看得到这个入口，而且只能在「信息编辑员 ↔ 普通用户」之间切换。
      为什么不做成下拉直接改：改角色会**立刻改变对方能进的后台页面**（编辑员能改
      全站内容），属于要"看一眼再确认"的操作；同时弹窗里能写清"对方需要重新登录才生效"。
    -->
    <el-dialog
      v-model="roleDialogVisible"
      :title="t('adminUsers.roleDialogTitle')"
      width="480px"
      :close-on-click-modal="false"
    >
      <p class="role-target">
        <i class="fas fa-user-gear"></i>
        {{ roleTarget?.username }}
      </p>

      <el-radio-group v-model="roleDraft" class="role-options">
        <el-radio value="USER">{{ t('adminUsers.roleUser') }}</el-radio>
        <el-radio value="EDITOR">{{ t('adminUsers.roleEditor') }}</el-radio>
      </el-radio-group>

      <!--
        第 128 批：内容模块勾选（内容审核 / 新闻管理 / 病害百科 / 意见反馈）
        ----------------------------------------------------------------
        选「信息编辑员」时才出现 —— 这四块**互不干扰**：只勾新闻管理的人，
        进后台只看到新闻管理（后端也会 403）。至少勾一项，否则他进后台什么也做不了。
      -->
      <div v-if="roleDraft === 'EDITOR'" class="role-modules">
        <p class="role-modules-title">
          <i class="fas fa-shield-halved"></i> {{ t('adminUsers.roleModulesTitle') }}
        </p>
        <el-checkbox-group v-model="moduleDraft">
          <el-checkbox v-for="module in moduleOptions" :key="module" :value="module">
            {{ t(`contentModule.${module}`) }}
          </el-checkbox>
        </el-checkbox-group>
        <p class="role-modules-hint">{{ t('adminUsers.roleModulesHint') }}</p>
        <!-- 第 179 批：同上 —— 改角色时也实时告诉他"这个人将能做什么" -->
        <EditorPermissionPreview :modules="moduleDraft" />
      </div>

      <el-alert type="info" :closable="false" show-icon class="role-note">
        <p>{{ t('adminUsers.roleDialogHint') }}</p>
      </el-alert>

      <template #footer>
        <el-button @click="roleDialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button
          type="primary"
          :loading="roleSubmitting"
          :disabled="roleDraft === 'EDITOR' && moduleDraft.length === 0"
          @click="submitRole"
        >
          {{ t('common.confirm') }}
        </el-button>
      </template>
    </el-dialog>

    <!--
      删除用户（第 95 批）
      ------------------------------------------------------------------
      为什么要求"手打一遍用户名"而不是普通的"确定/取消"：
      这是不可逆操作中最容易被点错的一个 —— 表格里每行都有按钮、旁边就是"取消专家"，
      弹窗一多就容易条件反射点确定。要求输入用户名能让操作者**确认自己点的是哪一行**。
      （服务端也要求同一个 confirm 字段，前端弹窗只是第一道。）
    -->
    <el-dialog
      v-model="deleteVisible"
      :title="t('adminUsers.deleteDialogTitle')"
      width="520px"
      :close-on-click-modal="false"
    >
      <el-alert type="warning" :closable="false" show-icon class="delete-warning">
        <p>{{ t('adminUsers.deleteWarning') }}</p>
        <p class="delete-warning-sub">{{ t('adminUsers.deleteKeepsContent') }}</p>
      </el-alert>

      <el-descriptions :column="2" border size="small" class="delete-target">
        <el-descriptions-item :label="t('adminUsers.fieldUsername')">
          {{ deleteTarget?.username }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('adminUsers.colRole')">
          {{ roleLabel(deleteTarget) }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('adminUsers.fieldPosts')">
          {{ deleteTarget?.post_count }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('adminUsers.fieldComments')">
          {{ deleteTarget?.comment_count }}
        </el-descriptions-item>
      </el-descriptions>

      <el-form label-position="top" class="delete-form">
        <el-form-item :label="t('adminUsers.deleteConfirmLabel', { name: deleteTarget?.username || '' })">
          <el-input
            v-model="deleteConfirmText"
            :placeholder="deleteTarget?.username || ''"
            autocomplete="off"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="deleteVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button
          type="danger"
          :loading="deleting"
          :disabled="deleteConfirmText.trim() !== (deleteTarget?.username || '')"
          @click="confirmDelete"
        >
          {{ t('adminUsers.deleteConfirmAction') }}
        </el-button>
      </template>
    </el-dialog>

    <!--
      批量删除用户（第 100 批）
      ------------------------------------------------------------------
      为什么批量删除**不要求逐行输入用户名**（单条删除要求）：一次选 10 个还要打 10 遍
      名字，等于把批量入口做成不可用。改成"列出要删的用户名 + 输入固定词确认"——
      让人能核对清单，又不至于点到手软。
      真正的护栏仍然在后端：不能删自己、不能删超管、非超管不能删管理员，
      而且**逐条**执行（部分失败会如实报告，不会"以为都删了"）。
    -->
    <el-dialog
      v-model="bulkDeleteVisible"
      :title="t('adminUsers.bulkDeleteTitle')"
      width="560px"
      :close-on-click-modal="false"
    >
      <el-alert type="warning" :closable="false" show-icon class="delete-warning">
        <p>{{ t('adminUsers.deleteWarning') }}</p>
        <p class="delete-warning-sub">{{ t('adminUsers.deleteKeepsContent') }}</p>
      </el-alert>

      <p class="bulk-list-title">
        {{ t('adminUsers.bulkDeleteList', { count: deletableSelected.length }) }}
      </p>
      <ul class="bulk-list">
        <li v-for="row in deletableSelected" :key="row.id">
          <span class="user-name">{{ row.username }}</span>
          <span class="muted">{{ roleLabel(row) }}</span>
        </li>
      </ul>

      <el-alert
        v-if="blockedSelected.length"
        type="info"
        :closable="false"
        show-icon
        class="bulk-blocked"
        :title="t('adminUsers.bulkDeleteSkipped', { count: blockedSelected.length })"
        :description="blockedSelected.map((r) => `${r.username}：${deleteBlockedReason(r)}`).join('；')"
      />

      <el-form label-position="top" class="delete-form">
        <el-form-item :label="t('adminUsers.bulkDeleteConfirmLabel', { word: bulkDeleteWord })">
          <el-input v-model="bulkDeleteConfirmText" :placeholder="bulkDeleteWord" autocomplete="off" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="bulkDeleteVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button
          type="danger"
          :loading="bulkDeleting"
          :disabled="!deletableSelected.length || bulkDeleteConfirmText.trim() !== bulkDeleteWord"
          @click="confirmBulkDelete"
        >
          {{ t('adminUsers.bulkDeleteConfirmAction', { count: deletableSelected.length }) }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
/**
 * 管理端「用户管理」（第 76 批新增）
 * ------------------------------------------------------------------
 * 背景：管理板块此前只有 新闻 / 意见反馈 / 内容审核 / 数据看板，
 * **没有用户管理** —— 管理员想看"平台上有哪些用户、谁是专家、谁多久没登录过"
 * 只能进 Django 自带的 /admin/（不在产品导航里，权限口径也不一致）。
 *
 * 本页只做**读** + 专家授予/取消：
 *   · 禁用账号 / 改角色 / 删除用户 属于不可逆或提权操作，本次明确不做；
 *   · 列表/详情走新增的 /api/admin/users/（只读）；
 *   · 授予与取消**复用**专家咨询域的现成接口（@/api/consult 的
 *     grantExpert / revokeExpert），不另造一套专家管理接口。
 *
 * 为什么不复用 /api/users/：那个接口用的是 UserProfileSerializer（面向"资料页"），
 * 不含角色中文名、专家身份、活跃度等管理端字段，且被"授予专家"的用户搜索复用，
 * 改它的返回结构会牵连咨询页。所以另开 /api/admin/users/。
 */
import { computed, ref, watch } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  bulkDeleteAdminUsers, createAdminResetLink, createEditorAccount, deleteAdminUser,
  fetchAdminUser, fetchAdminUsers, updateUserRole,
  updateUserStatus,   // 第 137 批：停用 / 恢复账号
} from '@/api/adminUser';
import EditorPermissionPreview from '@/components/EditorPermissionPreview.vue';  // 第 179 批：勾了模块=他能做什么
import { grantExpert, revokeExpert } from '@/api/consult';
import { formatApiError } from '@/api/http';
import { formatTime } from '@/utils/date';
import { useAuthStore } from '@/stores/auth';  // 第 95 批：判断"这行是不是我自己"
import { useI18n } from '@/i18n';
import { useQueryState } from '@/composables/useQueryState';  // 第 98 批：筛选/分页进 URL

export default {
  components: { EditorPermissionPreview },
  name: 'AdminUsersView',
  setup() {
    const { t } = useI18n();
    const authStore = useAuthStore();  // 第 95 批
    const currentUserId = computed(() => authStore.user?.id ?? null);
    const currentIsSuperuser = computed(() => Boolean(authStore.user?.is_superuser));

    const loading = ref(false);
    const items = ref([]);
    const total = ref(0);
    const page = ref(1);
    // 第 89 批：默认每页条数与意见反馈管理页对齐（原来 20，两页一个 10 一个 20，观感不一致）
    const pageSize = ref(10);
    const filters = ref({ search: '', role: '', status: '', scope: '' });   // 第 144 批：scope = 账号范围
    const stats = ref({ total: 0, staff: 0, expert: 0, normal: 0 });
    /** 第 100 批：后端排序（`?ordering=`），空串 = 默认按注册时间倒序 */
    const ordering = ref('');

    const detailVisible = ref(false);
    const detailLoading = ref(false);
    const detail = ref(null);

    const grantVisible = ref(false);
    const granting = ref(false);
    const grantTarget = ref(null);
    const grantForm = ref({ title: '', specialties: '' });

    // -- 删除用户（第 95 批）--------------------------------------------
    const deleteVisible = ref(false);
    const deleting = ref(false);
    const deleteTarget = ref(null);
    const deleteConfirmText = ref('');

    /**
     * 这行能不能删 —— **前端只负责"少让人白点一次"**，真正的护栏在后端：
     * 不能删自己、不能删超级管理员、非超管不能删其他管理员。
     * 这里做同样的判断并把原因写进 title，用户不用点了才知道。
     */
    const deleteBlockedReason = (row) => {
      if (!row) return '';
      if (row.id === currentUserId.value) return t('adminUsers.deleteBlockedSelf');
      if (row.is_superuser) return t('adminUsers.deleteBlockedSuperuser');
      if ((row.is_staff || row.role === 'ADMIN') && !currentIsSuperuser.value) {
        return t('adminUsers.deleteBlockedAdmin');
      }
      return '';
    };

    const canDelete = (row) => deleteBlockedReason(row) === '';

    // -- 停用 / 恢复账号（第 137 批）----------------------------------------
    /**
     * 这一行能不能停用/恢复 —— 与后端 `_check_status_allowed` **同一套口径**，
     * 而且是**删除护栏的真子集**（能删就一定能停用，不会出现"能删却不能停"的怪事）：
     *   · 不能停用自己（一按就把自己锁在管理端外面）；
     *   · 非超管不能停用权限不低于自己的账号。
     * 已删除（is_deleted）与注销冷静期的账号本来就不在列表里，所以这里不用判断。
     */
    const statusBlockedReason = (row) => {
      if (!row) return '';
      // 第 144 批：这两类账号由"删除/注销"流程管状态，用户管理里改不了（后端也是 404）
      if (row.is_deleted) return t('adminUsers.statusBlockedDeleted');
      if (isGraceAccount(row)) return t('adminUsers.statusBlockedGrace');
      if (row.id === currentUserId.value) return t('adminUsers.statusBlockedSelf');
      if ((row.is_staff || row.is_superuser || row.role === 'ADMIN') && !currentIsSuperuser.value) {
        return t('adminUsers.statusBlockedElevated');
      }
      return '';
    };

    const canToggleStatus = (row) => statusBlockedReason(row) === '';

    /**
     * 停用 / 恢复（带确认）
     *
     * 为什么停用要单独确认、而且措辞更重：它会让对方**立刻掉线**（后端顺手作废 token），
     * 并且**恢复后对方需要重新登录** —— 这两点不说清楚，管理员会以为"跟没停一样"。
     */
    const toggleStatus = async (row) => {
      const turningOff = row.is_active;
      try {
        await ElMessageBox.confirm(
          t(turningOff ? 'adminUsers.statusDisableConfirm' : 'adminUsers.statusEnableConfirm',
            { name: row.username }),
          t(turningOff ? 'adminUsers.statusDisableAction' : 'adminUsers.statusEnableAction'),
          {
            type: turningOff ? 'warning' : 'info',
            confirmButtonText: t(turningOff ? 'adminUsers.statusDisableAction' : 'adminUsers.statusEnableAction'),
            cancelButtonText: t('common.cancel'),
          },
        );
      } catch {
        return;   // 用户点了取消
      }
      try {
        const data = await updateUserStatus(row.id, !turningOff);
        // 后端会说清"对方现在能不能登"，比前端自己拼一句话更准（幂等时也会返回 changed=false）
        ElMessage.success(data?.message || t(turningOff
          ? 'adminUsers.statusDisabledOk' : 'adminUsers.statusEnabledOk', { name: row.username }));
        await reload();
        if (detail.value?.id === row.id) detail.value = data?.user || detail.value;
      } catch (error) {
        ElMessage.error(formatApiError(
          error, t(turningOff ? 'adminUsers.statusDisableFailed' : 'adminUsers.statusEnableFailed')));
      }
    };

    // -- 签发一次性密码重置链接（第 120 批）------------------------------
    // 场景：账号**没绑邮箱**时自助找回密码是静默失败的（后端按防枚举策略什么都不做，
    // 页面却显示"已发送"）。管理端账号大多由超管开通、常常没绑邮箱 ——
    // 所以这里给管理员一条能走通的路：签发链接 → 线下发给本人 → 本人自己设新密码。
    const resetLinkVisible = ref(false);
    const resetLinkLoading = ref(false);
    const resetLinkTarget = ref(null);
    const resetLinkData = ref(null);
    const resetLinkError = ref('');

    /**
     * 这行能不能签发重置链接 —— 与后端 `_check_reset_allowed` **同一套口径**：
     *   · 已停用/已注销的不签发；
     *   · 非超管不能给"权限不低于自己"的账号签发（否则等于顶号，是提权）。
     * 前端这份只是"别让人白点一次"，真正的护栏在后端。
     */
    const resetLinkBlockedReason = (row) => {
      if (!row) return '';
      // 第 144 批：区分"已注销"与"停用/冷静期"——前者重置了也没人能登录
      if (row.is_deleted) return t('adminUsers.resetBlockedDeleted');
      if (!row.is_active) return t('adminUsers.resetBlockedInactive');
      if (row.id === currentUserId.value) return '';   // 自己：允许（本来就登着）
      if ((row.is_staff || row.is_superuser || row.role === 'ADMIN') && !currentIsSuperuser.value) {
        return t('adminUsers.resetBlockedElevated');
      }
      return '';
    };

    const canResetLink = (row) => resetLinkBlockedReason(row) === '';

    // -- 改角色（第 127 批）------------------------------------------------
    // 产品决策 #4：**只有超级管理员**能在 Console 里改角色，且只能在
    // 「信息编辑员 EDITOR ↔ 普通用户 USER」之间调；ADMIN 只能走 Django admin。
    // 后端 `AdminUserRoleView` 有同样的四条护栏，这里只是"别把做不到的按钮画出来"。
    const roleDialogVisible = ref(false);
    const roleSubmitting = ref(false);
    const roleTarget = ref(null);
    const roleDraft = ref('USER');
    // 第 128 批：内容模块勾选（review / news / pests / feedback）
    const moduleOptions = authStore.CONTENT_MODULES;
    const moduleDraft = ref([]);

    /** 这一行能不能改角色（不能改自己、不能改管理员/staff/超管） */
    const canChangeRole = (row) => Boolean(
      row
      && currentIsSuperuser.value
      && !row.is_deleted            // 第 144 批：已注销账号不改角色
      && !isGraceAccount(row)       // 第 144 批：冷静期账号也不改
      && row.id !== currentUserId.value
      && !row.is_staff
      && !row.is_superuser
      && row.role !== 'ADMIN'
      && (row.role === 'EDITOR' || row.role === 'USER'),
    );

    const openRoleDialog = (row) => {
      roleTarget.value = row;
      roleDraft.value = row.role === 'EDITOR' ? 'EDITOR' : 'USER';
      // 回填他现有的模块（后端在列表里给了 content_modules）；新建的编辑员默认全勾
      const existing = Array.isArray(row.content_modules) ? row.content_modules : [];
      moduleDraft.value = existing.length ? [...existing] : [...moduleOptions];
      roleDialogVisible.value = true;
    };

    const submitRole = async () => {
      const row = roleTarget.value;
      if (!row) return;
      const isEditor = roleDraft.value === 'EDITOR';
      if (isEditor && moduleDraft.value.length === 0) return;   // 按钮已禁用，这里兜底
      if (roleDraft.value === row.role && (!isEditor || sameModules(row))) {
        roleDialogVisible.value = false;   // 没改就当作取消
        return;
      }
      roleSubmitting.value = true;
      try {
        const result = await updateUserRole(
          row.id, roleDraft.value, isEditor ? moduleDraft.value : undefined,
        );
        const modules = result?.content_modules || [];
        ElMessage.success(
          result?.role === 'EDITOR'
            ? t('adminUsers.roleChangedWithModules', {
                name: row.username,
                modules: modules.map((m) => t(`contentModule.${m}`)).join('、'),
              })
            : t('adminUsers.roleChanged', {
                name: row.username,
                role: roleLabel({ role: result?.role || roleDraft.value }),
              }),
        );
        roleDialogVisible.value = false;
        await loadList();   // 刷新这一页（角色标签、模块标签与筛选结果都会变）
      } catch (error) {
        ElMessage.error(formatApiError(error, t('adminUsers.roleChangeFailed')));
      } finally {
        roleSubmitting.value = false;
      }
    };

    /** 弹窗里的模块选择与库里一致？（用于"没改就当作取消"的判断） */
    const sameModules = (row) => {
      const existing = Array.isArray(row.content_modules) ? [...row.content_modules].sort() : [];
      const draft = [...moduleDraft.value].sort();
      return existing.length === draft.length && existing.every((m, i) => m === draft[i]);
    };

    // -- 开通编辑员账号（第 131 批）----------------------------------------
    // 仅超管；账号无可用密码 + 一次性设置密码链接。与"改角色"是同一类提权操作，
    // 因此护栏也一致（后端 AdminUserCreateEditorView 会再校验一遍）。
    const createEditorVisible = ref(false);
    const creatingEditor = ref(false);
    const createEditorForm = ref({ username: '', email: '' });
    const createEditorModules = ref([]);
    const createdEditor = ref(null);   // 非空 = 已建好，弹窗切到"给链接"那一步

    const canCreateEditor = computed(() => currentIsSuperuser.value);

    const openCreateEditor = () => {
      createEditorForm.value = { username: '', email: '' };
      createEditorModules.value = [...moduleOptions];   // 默认全勾，再按需去掉
      createdEditor.value = null;
      createEditorVisible.value = true;
    };

    const resetCreateEditor = () => {
      createEditorForm.value = { username: '', email: '' };
      createdEditor.value = null;
    };

    const submitCreateEditor = async () => {
      creatingEditor.value = true;
      try {
        const result = await createEditorAccount({
          username: createEditorForm.value.username.trim(),
          email: createEditorForm.value.email.trim(),
          modules: createEditorModules.value,
        });
        createdEditor.value = result;
        await loadList();   // 列表里立刻能看到新账号
      } catch (error) {
        ElMessage.error(formatApiError(error, t('adminUsers.createEditorFailed')));
      } finally {
        creatingEditor.value = false;
      }
    };

    /** 复制设置密码链接（与"重置密码"共用同一套提示） */
    const copyCreatedEditorLink = async () => {
      const url = createdEditor.value?.url || '';
      if (!url) return;
      try {
        await navigator.clipboard.writeText(url);
        ElMessage.success(t('adminUsers.resetLinkCopied'));
      } catch {
        ElMessage.warning(t('adminUsers.resetLinkCopyManual'));
      }
    };

    const openResetLink = async (row) => {
      resetLinkTarget.value = row;
      resetLinkData.value = null;
      resetLinkError.value = '';
      resetLinkVisible.value = true;
      resetLinkLoading.value = true;
      try {
        resetLinkData.value = await createAdminResetLink(row.id);
      } catch (error) {
        resetLinkError.value = formatApiError(error, t('adminUsers.resetLinkFailed'));
      } finally {
        resetLinkLoading.value = false;
      }
    };

    /** 复制链接：失败不抛错（http / 非安全上下文下 clipboard 可能不可用），给一句提示 */
    const copyResetLink = async () => {
      const url = resetLinkData.value?.url || '';
      if (!url) return;
      try {
        await navigator.clipboard.writeText(url);
        ElMessage.success(t('adminUsers.resetLinkCopied'));
      } catch {
        ElMessage.warning(t('adminUsers.resetLinkCopyManual'));
      }
    };

    const openDelete = (row) => {
      deleteTarget.value = row;
      deleteConfirmText.value = '';
      deleteVisible.value = true;
    };

    const confirmDelete = async () => {
      if (!deleteTarget.value) return;
      const row = deleteTarget.value;
      deleting.value = true;
      try {
        await deleteAdminUser(row.id, deleteConfirmText.value.trim());
        ElMessage.success(t('adminUsers.deleteOk', { name: row.username }));
        deleteVisible.value = false;
        // 删掉的可能是本页最后一条 → 与反馈管理页同一处理，避免停在空白页
        if (items.value.length === 1 && page.value > 1) page.value -= 1;
        await reload();
      } catch (error) {
        ElMessage.error(formatApiError(error, t('adminUsers.deleteFailed')));
      } finally {
        deleting.value = false;
      }
    };

    // ======================================================================
    // 第 100 批：批量删除 + 后端排序
    // ======================================================================
    const userTableRef = ref(null);
    const selectedRows = ref([]);
    const bulkDeleteVisible = ref(false);
    const bulkDeleting = ref(false);
    const bulkDeleteConfirmText = ref('');
    /** 批量删除要求输入的确认词（与单条删除"输入用户名"同一个思路，只是不必逐行打） */
    const bulkDeleteWord = 'DELETE';

    const onSelectionChange = (rows) => {
      selectedRows.value = rows || [];
    };

    /** 不可删的行不让勾选 —— 与其勾完再被拒，不如一开始就点不动（原因在按钮 title 里） */
    const isRowSelectable = (row) => canDelete(row);

    const clearSelection = () => {
      userTableRef.value?.clearSelection?.();
      selectedRows.value = [];
    };

    /** 选中的行里**真正可删**的（护栏与后端一致：见 deleteBlockedReason） */
    const deletableSelected = computed(() => selectedRows.value.filter((row) => canDelete(row)));
    const blockedSelected = computed(() => selectedRows.value.filter((row) => !canDelete(row)));

    const openBulkDelete = () => {
      bulkDeleteConfirmText.value = '';
      bulkDeleteVisible.value = true;
    };

    const confirmBulkDelete = async () => {
      const rows = deletableSelected.value;
      if (!rows.length) return;
      bulkDeleting.value = true;
      try {
        const result = await bulkDeleteAdminUsers(rows.map((row) => row.id));
        const succeeded = result?.succeeded ?? 0;
        const failed = result?.failed ?? 0;
        if (failed > 0) {
          // 有失败就**说清楚哪几条为什么失败** —— 只说"部分失败"等于没说
          const reasons = (result?.results || [])
            .filter((item) => !item.ok)
            .map((item) => {
              const row = rows.find((r) => r.id === item.id);
              return `${row?.username || item.id}：${item.detail}`;
            })
            .join('；');
          ElMessage.warning(t('adminUsers.bulkDeletePartial', { ok: succeeded, failed }) + reasons);
        } else {
          ElMessage.success(t('adminUsers.bulkDeleteOk', { count: succeeded }));
        }
        bulkDeleteVisible.value = false;
        clearSelection();
        // 整页都被删掉时退回上一页（否则停在空白页）
        if (succeeded >= items.value.length && page.value > 1) page.value -= 1;
        await reload();
      } catch (error) {
        ElMessage.error(formatApiError(error, t('adminUsers.deleteFailed')));
      } finally {
        bulkDeleting.value = false;
      }
    };

    /**
     * 表头排序 → 交给后端（`sortable="custom"`）
     *
     * ⚠️ 三个坑都踩过（第 100 批）：
     *  1. 一定要**回到第 1 页**：排序换了之后原页码可能越界，后端对越界页返回 404，页面空白；
     *  2. `ordering` 必须登记进 `useQueryState`，否则后端收不到参数、地址栏也不变
     *     （表现：点了表头没反应）；
     *  3. **el-table 记不住 `sortable="custom"` 的排序状态**：数据一旦被后端重排后整体替换，
     *     它的内部排序状态就没了，于是第二次点同一列拿到的是 `null`（"取消排序"），
     *     而不是"切到升序"。试过用 `:default-sort` 把状态喂回去，实测**无效**（仍是 descending→null）。
     *     最终改为**自己维护三态循环**：拿到 el-table 的原始意图后，按"降序 → 升序 → 取消"
     *     推进（以我们自己记住的 `ordering` 为准，不依赖组件的内部状态）。
     */
    const onSortChange = ({ prop, order }) => {
      const next = order ? `${order === 'descending' ? '-' : ''}${prop}` : '';
      // 以"当前 ordering"推下一步；这正是"不依赖 el-table 记忆"的关键
      let target;
      if (!ordering.value) {
        target = `-${prop}`;                       // 未排序 → 降序（与 el-table 的首次行为一致）
      } else if (ordering.value === `-${prop}`) {
        target = prop;                             // 降序 → 升序
      } else if (ordering.value === prop) {
        target = '';                               // 升序 → 取消排序
      } else {
        target = next || `-${prop}`;               // 换了另一列：从降序开始
      }

      console.debug('[admin-users] 表头排序:', prop, order, '=>', target || '(默认)');
      ordering.value = target;
      page.value = 1;
      loadList();
    };

    // -- 展示映射（角色的中文名由前端给，切语言时才跟着变） ----------------
    const roleLabel = (row) => ({
      ADMIN: t('adminUsers.roleAdmin'),
      EDITOR: t('adminUsers.roleEditor'),
      USER: t('adminUsers.roleUser'),
    }[row?.role] || row?.role || '');

    const roleTagType = (row) => ({
      ADMIN: 'danger',
      EDITOR: 'warning',
      USER: 'info',
    }[row?.role] || 'info');

    // 「账号状态」只表达可用性；管理员/专家身份各有独立标签，避免一个格子塞三种含义
    /**
     * 账号状态标签（第 144 批拆细）
     *
     * 以前只有两档：is_active 为真 → "正常"，否则 → "已禁用"。但"不可用"其实有三种，
     * 而**该做什么完全不同**：
     *   · 已删除（软删除，用户名都让出去了）→ 什么都做不了，只能看；
     *   · 注销冷静期 → 由本人登录取消注销，管理员不代为恢复；
     *   · 被管理员停用 → 可以「恢复」。
     * 混成一个"已禁用"，管理员就会对着冷静期账号找"恢复"按钮（而那个按钮是 404）。
     */
    const isGraceAccount = (row) => Boolean(row && !row.is_deleted && row.deletion_scheduled_for);

    const statusTagType = (row) => {
      if (!row) return 'info';
      if (row.is_deleted) return 'info';
      if (isGraceAccount(row)) return 'warning';
      return row.is_active === false ? 'danger' : 'success';
    };

    const statusLabel = (row) => {
      if (!row) return '';
      if (row.is_deleted) return t('adminUsers.statusDeleted');
      if (isGraceAccount(row)) {
        // 剩余天数是**后端算的**（冷静期长度可配置，前端不写死）
        return row.deletion_days_left === null || row.deletion_days_left === undefined
          ? t('adminUsers.statusGrace')
          : t('adminUsers.statusGraceDays', { days: row.deletion_days_left });
      }
      return row.is_active === false ? t('adminUsers.statusDisabled') : t('adminUsers.statusActive');
    };

    const fullName = (row) => [row?.last_name, row?.first_name].filter(Boolean).join(' ').trim();

    // -- 数据加载 ---------------------------------------------------------
    const buildParams = () => {
      const params = { page: page.value, page_size: pageSize.value };
      if (filters.value.search.trim()) params.search = filters.value.search.trim();
      if (filters.value.role) params.role = filters.value.role;
      if (filters.value.status) params.status = filters.value.status;
      // 第 144 批：账号范围 —— 已注销 / 注销冷静期（端点早就支持，界面上此前没有开关）。
      // ⚠️ 两条参数**不能同时发**：include_deleted 让后端返回"全部账号"（含正常），
      //    pending_deletion 则是"只看冷静期"，按当前选择二选一。
      if (filters.value.scope === 'include_deleted') params.include_deleted = 'true';
      if (filters.value.scope === 'pending_deletion') params.pending_deletion = 'true';
      // 第 100 批：排序交后端（白名单字段，后端会忽略非法值）
      if (ordering.value) params.ordering = ordering.value;
      return params;
    };

    const loadList = async () => {
      loading.value = true;
      try {
        const data = await fetchAdminUsers(buildParams());
        items.value = data.results || [];
        total.value = data.count || 0;
      } catch (error) {
        ElMessage.error(formatApiError(error, t('adminUsers.loadFailed')));
      } finally {
        loading.value = false;
      }
    };

    // 概览小卡：各用一次 page_size=1 的请求只取 count（与反馈管理页同一套路）
    const loadStats = async () => {
      try {
        const [all, staff, expert, normal] = await Promise.all([
          fetchAdminUsers({ page: 1, page_size: 1 }),
          fetchAdminUsers({ page: 1, page_size: 1, status: 'staff' }),
          fetchAdminUsers({ page: 1, page_size: 1, status: 'expert' }),
          fetchAdminUsers({ page: 1, page_size: 1, role: 'USER' }),
        ]);
        stats.value = {
          total: all?.count || 0,
          staff: staff?.count || 0,
          expert: expert?.count || 0,
          normal: normal?.count || 0,
        };
      } catch (error) {
        console.warn('获取用户统计失败:', error);
      }
    };

    const reload = async () => {
      await Promise.all([loadList(), loadStats()]);
    };

    // ========================================================================
    // 第 98 批：筛选与分页写进 URL
    // ------------------------------------------------------------------------
    // 此前只存在组件内存里 → 刷新即重置、后退丢条件、也没法把"这一页结果"分享出去。
    // 用 `filters.value.xxx` 作为 ref 传入：对象属性本身不是 ref，包一层 getter/setter
    // 让 useQueryState 能读能写，同时保持模板里 `filters.search` 的写法不变。
    // ========================================================================
    const filterRef = (key) => ({
      get value() { return filters.value[key]; },
      set value(next) { filters.value[key] = next ?? ''; },
    });

    const { isReady: queryReady } = useQueryState({
      fields: {
        page: { ref: page, type: 'int', default: 1 },
        page_size: { ref: pageSize, type: 'int', default: 10 },
        search: { ref: filterRef('search'), type: 'string', default: '' },
        role: { ref: filterRef('role'), type: 'string', default: '' },
        status: { ref: filterRef('status'), type: 'string', default: '' },
        // 第 144 批：账号范围也要进 URL —— 第 100 批那次教训（ordering 没登记 → 点了表头没反应）
        // 在这里同样适用：不进 URL 的话刷新/后退/把链接发给同事都会**丢掉这个筛选**，
        // 于是"我明明筛出了已注销账号，别人打开却看不到"。
        scope: { ref: filterRef('scope'), type: 'string', default: '' },
        // ⚠️ 排序也必须登记进来（第 100 批的坑）：`tableSortOrdering` 自己改了 ref，
        // 但没告诉 useQueryState，于是**后端收不到 ordering、地址栏也不变** ——
        // 表现是"点了表头没反应"。实测诊断日志里 onSortChange 已经算出
        // `date_joined descending`，URL 却还是 null。
        ordering: { ref: ordering, type: 'string', default: '' },
      },
      // URL 变（后退/前进/别人发来的链接）→ 重新查一次
      onExternalChange: () => reload(),
    });

    /**
     * 改筛选条件：**回到第 1 页**再查。
     * 不重置页码会出现"在第 5 页筛出 3 条、页面空白"（后端分页对越界页返回 404）。
     */
    const applyFilter = () => {
      page.value = 1;
      loadList();
    };

    /**
     * 点下拉的清除图标（第 88 批）
     *
     * el-select 清除时走 deleteSelected()：`emitChange(value)` 之后才 `emit('clear')`，
     * 而 emitChange 内部有一道 `if (!isEqual(props.modelValue, val))` 守卫
     * （element-plus/es/components/select/src/useSelect.mjs）—— 清除的意图是明确的，
     * 却要先比一遍"值有没有变"才决定通不通知页面。
     *
     * 所以筛选不能只挂在 @change 上：一旦那次 change 被守卫挡掉，列表就停在原来的
     * 筛选结果里，用户看到的就是"选了角色只能看当前的，清不掉、看不到全部"。
     * `clear` 是无条件发出的，挂它最稳（即便 change 也发了，最坏只是多查一次，幂等）。
     */
    const handleClear = () => applyFilter();

    const hasFilter = computed(() =>
      Boolean(filters.value.role || filters.value.status || filters.value.scope
        || filters.value.search.trim()),
    );

    /** 一键回到全部用户：把三个条件一起清掉再查 */
    const resetFilters = () => {
      filters.value = { search: '', role: '', status: '', scope: '' };
      applyFilter();
    };

    /**
     * 改每页条数时回到第 1 页。
     * 否则"在第 5 页把每页条数改成 50"会让 page 越界，后端分页直接 404（页面空白）。
     */
    const handleSizeChange = () => {
      page.value = 1;
      loadList();
    };

    // -- 详情 -------------------------------------------------------------
    const openDetail = async (row) => {
      detailVisible.value = true;
      detailLoading.value = true;
      detail.value = null;
      try {
        detail.value = await fetchAdminUser(row.id);
      } catch (error) {
        ElMessage.error(formatApiError(error, t('adminUsers.detailFailed')));
        detailVisible.value = false;
      } finally {
        detailLoading.value = false;
      }
    };

    // -- 授予 / 取消专家 ---------------------------------------------------
    const openGrant = (row) => {
      grantTarget.value = row;
      grantForm.value = { title: row.expert_title || '', specialties: (row.expert_specialties || []).join(',') };
      grantVisible.value = true;
    };

    const submitGrant = async () => {
      if (!grantTarget.value) return;
      granting.value = true;
      try {
        await grantExpert(grantTarget.value.id, {
          title: grantForm.value.title.trim(),
          specialties: grantForm.value.specialties.trim(),
        });
        ElMessage.success(t('adminUsers.grantedOk'));
        grantVisible.value = false;
        await reload();
        if (detail.value?.id === grantTarget.value.id) {
          detail.value = await fetchAdminUser(grantTarget.value.id);
        }
      } catch (error) {
        ElMessage.error(formatApiError(error, t('adminUsers.grantFailed')));
      } finally {
        granting.value = false;
      }
    };

    const doRevoke = async (row) => {
      try {
        await ElMessageBox.confirm(
          t('adminUsers.revokeConfirm', { name: row.username }),
          t('adminUsers.revokeAction'),
          { type: 'warning', confirmButtonText: t('adminUsers.revokeAction'), cancelButtonText: t('common.cancel') },
        );
      } catch {
        return; // 用户点了取消
      }
      try {
        await revokeExpert(row.id);
        ElMessage.success(t('adminUsers.revokeOk'));
        await reload();
        if (detail.value?.id === row.id) {
          detail.value = await fetchAdminUser(row.id);
        }
      } catch (error) {
        ElMessage.error(formatApiError(error, t('adminUsers.revokeFailed')));
      }
    };

    // 第 98 批：等 URL 参数应用完再加载（否则"带参数打开链接"会先用默认值查一次，
    // 再用链接里的条件查第二次 —— 两次请求、还会闪一下）
    watch(queryReady, (ready) => {
      if (ready) reload();
    }, { immediate: true });
    // 注意：不再用 onMounted(reload)，由上面的 watch 统一负责（避免重复加载）

    return {
      t,
      loading, items, total, page, pageSize, filters, stats,
      detailVisible, detailLoading, detail,
      grantVisible, granting, grantTarget, grantForm,
      roleLabel, roleTagType, statusLabel, statusTagType, fullName, formatTime,
      reload, loadList, applyFilter, handleSizeChange, openDetail, openGrant, submitGrant, doRevoke,
      // 第 88 批：清除筛选 / 一键回到全部用户
      handleClear, hasFilter, resetFilters,
      // 第 95 批：删除用户
      deleteVisible, deleting, deleteTarget, deleteConfirmText,
      canDelete, deleteBlockedReason, openDelete, confirmDelete,
      // 第 137 批：停用 / 恢复账号（模板里的按钮与确认框要用到）
      canToggleStatus, statusBlockedReason, toggleStatus,
      // 第 100 批：批量删除 + 后端排序
      userTableRef, selectedRows, onSelectionChange, isRowSelectable, clearSelection,
      bulkDeleteVisible, bulkDeleting, bulkDeleteConfirmText, bulkDeleteWord,
      deletableSelected, blockedSelected, openBulkDelete, confirmBulkDelete,
      onSortChange,
      // 第 120 批：签发一次性密码重置链接
      resetLinkVisible, resetLinkLoading, resetLinkTarget, resetLinkData, resetLinkError,
      canResetLink, resetLinkBlockedReason, openResetLink, copyResetLink,
      // 第 127 批：改角色（超级管理员 + 普通账号 才出现）
      canChangeRole, roleDialogVisible, roleSubmitting, roleTarget, roleDraft,
      openRoleDialog, submitRole, roleLabel,
      // 第 128 批：改角色时勾选内容模块
      moduleOptions, moduleDraft,
      // 第 131 批：开通编辑员账号
      canCreateEditor, createEditorVisible, creatingEditor, createEditorForm,
      createEditorModules, createdEditor, openCreateEditor, submitCreateEditor,
      copyCreatedEditorLink, resetCreateEditor,   // resetCreateEditor 被模板的 @closed 用到
    };
  },
};
</script>

<style scoped>
/* 第 117 批：删掉了 `.admin-users > .back-button` 的间距规则（返回按钮已随管理后台外壳一起移除） */

/* 第 131 批：开通编辑员弹窗里的成功提示 */
.create-editor-ok {
  margin-bottom: 12px;
}

.create-editor-ok p {
  margin: 0;
  line-height: 1.7;
}

/* 第 127 批：改角色弹窗 */
.role-target {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 14px;
  font-size: 14px;
  font-weight: 700;
  color: var(--ink-800, #24352c);
}

.role-options {
  display: flex;
  gap: 18px;
  margin-bottom: 14px;
}

/* 第 128 批：内容模块勾选区 */
.role-modules {
  margin: 0 0 14px;
  padding: 12px 14px;
  border: 1px solid var(--border, #e2ebe5);
  border-radius: 10px;
  background: var(--ink-50, #f8fbf9);
}

.role-modules-title {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 700;
  color: var(--ink-800, #24352c);
}

.role-modules-hint {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.7;
  color: var(--ink-500, #78897f);
}

.role-note {
  margin-top: 4px;
}

.role-note p {
  margin: 0;
  line-height: 1.7;
}

/* 第 120 批：签发密码重置链接弹窗 */
.reset-link-target {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 700;
  color: var(--ink-800, #24352c);
}

.reset-link-warning {
  margin-bottom: 14px;
}

.reset-link-warning p {
  margin: 0;
  line-height: 1.7;
}

.reset-link-sub {
  margin-top: 4px !important;
  font-size: 12.5px;
  opacity: 0.9;
}

/* 链接框：等宽字体 + 可整段选中，方便手动复制（clipboard 不可用时也有退路） */
.reset-link-box {
  display: flex;
  align-items: center;
  gap: 10px;
}

.reset-link-input {
  flex: 1;
  min-width: 0;
  height: 38px;
  padding: 0 12px;
  border: 1px solid var(--border-strong, #d3dfd8);
  border-radius: 10px;
  background: var(--ink-50, #f8fbf9);
  color: var(--ink-700, #3a4d43);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12.5px;
}

.reset-link-hint {
  margin: 14px 0 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--ink-500, #78897f);
}

.reset-link-hint i {
  margin-right: 6px;
  color: var(--brand-500, #3d9a68);
}

/* 第 95 批：删除用户弹窗里的提示与目标信息 */
.delete-warning {
  margin-bottom: 14px;
}

.delete-warning p {
  margin: 0;
  line-height: 1.7;
}

.delete-warning-sub {
  margin-top: 6px;
  font-size: 12.5px;
  opacity: 0.85;
}

.delete-target {
  margin-bottom: 14px;
}

.delete-form {
  margin-top: 4px;
}

/* 第 100 批：批量删除弹窗里的清单 */
.bulk-list-title {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 700;
  color: var(--ink-800, #24352c);
}

.bulk-list {
  margin: 0 0 14px;
  padding: 0;
  list-style: none;
  max-height: 220px;
  overflow-y: auto;
  border: 1px solid var(--border, #e2ebe5);
  border-radius: 8px;
}

.bulk-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 7px 12px;
  font-size: 13px;
  border-bottom: 1px solid var(--border, #e2ebe5);
}

.bulk-list li:last-child {
  border-bottom: none;
}

.bulk-blocked {
  margin-bottom: 14px;
}

/* 批量操作条里的"已选 N 人" */
.selection-hint {
  font-size: 13px;
  font-weight: 700;
  color: var(--danger, #cf4436);
  margin-right: 4px;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin: 14px 0;
}

.user-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.user-cell-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.user-name {
  font-weight: 700;
  color: var(--ink-800);
}

.user-email {
  font-size: 12px;
  color: var(--ink-400);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 第 128 批：编辑员的模块标签（列表里一眼看出"他管哪几块"） */
.user-modules {
  margin-top: 2px;
  font-size: 11.5px;
  color: var(--brand-600, #2f7d54);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-modules i {
  margin-right: 4px;
  font-size: 10.5px;
}

.expert-tag {
  margin-left: 6px;
}

.activity-text {
  font-size: 12.3px;
  color: var(--ink-600);
}

.muted {
  color: var(--ink-400);
  font-size: 12.3px;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}

.table-empty {
  padding: 26px 0;
  color: var(--ink-400);
  text-align: center;
}

.table-empty i {
  font-size: 26px;
}

.detail-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.detail-name {
  font-size: 15px;
  color: var(--ink-900);
}

.detail-tags {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 5px;
}

.detail-section {
  margin: 16px 0 8px;
  font-size: 13.3px;
  font-weight: 800;
  color: var(--ink-800);
}

:deep(.el-tag + .el-tag) {
  margin-left: 0;
}
</style>
