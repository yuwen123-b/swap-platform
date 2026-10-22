<template>
  <ProfileSubLayout title="位置管理" desc="设置你的位置后即可使用「离我最近」，是否对外公开由你决定">
    <!-- 当前位置 -->
    <section class="profile-card">
      <h2 class="card-title">当前位置</h2>

      <div class="setting-item">
        <div class="setting-text">
          <div class="setting-name">位置坐标</div>
          <div class="setting-desc">
            <template v-if="hasCoordinates">
              经度 {{ longitude.toFixed(4) }}，纬度 {{ latitude.toFixed(4) }}
            </template>
            <template v-else>尚未设置位置，设置后即可使用「离我最近」</template>
          </div>
        </div>
      </div>

      <div class="setting-item">
        <div class="setting-text">
          <div class="setting-name">所在小区</div>
          <div class="setting-desc">{{ profile?.community || '未设置' }}</div>
        </div>
      </div>

      <div class="setting-item">
        <div class="setting-text">
          <div class="setting-name">楼栋</div>
          <div class="setting-desc">{{ profile?.building || '未设置' }}</div>
        </div>
      </div>

      <div class="form-actions">
        <el-button type="primary" :loading="locating" @click="useCurrentLocation">
          定位当前位置
        </el-button>
        <el-button v-if="hasCoordinates" link type="danger" :loading="saving" @click="clearLocation">
          清除位置
        </el-button>
      </div>
    </section>

    <!-- 手动输入地址 -->
    <section class="profile-card">
      <h2 class="card-title">手动输入地址</h2>
      <p class="card-hint">
        输入完整地址（如「山西省吕梁市离石区 XX 小区 3 号楼」），系统会解析出坐标、小区与楼栋。
      </p>
      <div class="form-item">
        <el-input
          v-model="addressDraft"
          type="textarea"
          :rows="2"
          maxlength="120"
          show-word-limit
          placeholder="请输入详细地址"
        />
      </div>
      <div class="form-actions">
        <el-button :loading="searching" @click="onSearchAddress">解析并保存</el-button>
      </div>
    </section>

    <!-- 公开开关 -->
    <section class="profile-card">
      <h2 class="card-title">隐私设置</h2>
      <div class="setting-item">
        <div class="setting-text">
          <div class="setting-name">公开我的位置</div>
          <div class="setting-desc">
            开启后，其他用户使用「离我最近」时可以找到你的物品；关闭后仅你自己可见。
          </div>
        </div>
        <el-switch
          v-model="locationPublic"
          size="large"
          aria-label="公开我的位置"
          :loading="saving"
          @change="onLocationPublicChange"
        />
      </div>
    </section>
  </ProfileSubLayout>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import ProfileSubLayout from '../../layouts/ProfileSubLayout.vue'
import { getProfile, searchAddress, updateProfile } from '../../api/user'

const profile = ref(null)
const locationPublic = ref(false)
const latitude = ref(0)
const longitude = ref(0)
const saving = ref(false)
const locating = ref(false)
const searching = ref(false)
const addressDraft = ref('')

const hasCoordinates = computed(() => latitude.value !== 0 || longitude.value !== 0)

function syncFromProfile(data) {
  profile.value = data
  locationPublic.value = Number(data?.location_public || 0) === 1
  latitude.value = Number(data?.latitude || 0)
  longitude.value = Number(data?.longitude || 0)
}

async function loadProfile() {
  try {
    syncFromProfile(await getProfile())
  } catch {
    // 错误提示由请求拦截器统一处理
  }
}

// 公开开关：单独提交 location_public，未设置坐标时拒绝开启
async function onLocationPublicChange(value) {
  if (value && !hasCoordinates.value) {
    locationPublic.value = false
    ElMessage.warning('请先设置位置坐标，再开启公开')
    return
  }
  saving.value = true
  try {
    syncFromProfile(await updateProfile({ location_public: value ? 1 : 0 }))
    ElMessage.success(value ? '位置已公开' : '位置已设为不公开')
  } catch {
    locationPublic.value = !value
    ElMessage.error('保存失败，请稍后再试')
  } finally {
    saving.value = false
  }
}

// 浏览器定位：写入坐标，规则要求默认不公开
function useCurrentLocation() {
  if (!navigator.geolocation) {
    ElMessage.warning('当前浏览器不支持定位，请手动输入地址')
    return
  }
  locating.value = true
  navigator.geolocation.getCurrentPosition(
    async (pos) => {
      locating.value = false
      const lat = Number(pos.coords.latitude.toFixed(6))
      const lng = Number(pos.coords.longitude.toFixed(6))
      saving.value = true
      try {
        syncFromProfile(await updateProfile({ latitude: lat, longitude: lng, location_public: 0 }))
        ElMessage.success('位置已更新，默认不公开')
      } catch {
        ElMessage.error('位置保存失败，请稍后再试')
      } finally {
        saving.value = false
      }
    },
    () => {
      locating.value = false
      ElMessage.warning('定位失败，请检查浏览器定位权限')
    },
    { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 },
  )
}

// 手动输入地址 -> 后端地理编码 -> 再保存坐标与地址信息
async function onSearchAddress() {
  const address = addressDraft.value.trim()
  if (address.length < 2) {
    ElMessage.warning('请输入至少 2 个字的地址')
    return
  }
  searching.value = true
  try {
    // 自己处理失败提示，避免两条 toast 叠加
    const geo = await searchAddress({ address }, { skipErrorToast: true })
    syncFromProfile(
      await updateProfile({
        latitude: geo.latitude,
        longitude: geo.longitude,
        community: geo.community || undefined,
        building: geo.building || undefined,
      }),
    )
    addressDraft.value = ''
    ElMessage.success('地址已解析并保存')
  } catch (error) {
    const status = error?.response?.status
    const serverMsg = error?.response?.data?.message || ''
    if (status === 501) {
      // 后端未配置高德 Key：给可执行的引导，而不是技术文案
      ElMessage.warning('地址解析未配置，请改用「定位当前位置」')
    } else if (status === 401) {
      // 登录态失效：已由请求拦截器跳转登录页
    } else {
      ElMessage.error(serverMsg || '地址解析失败，请稍后重试')
    }
  } finally {
    searching.value = false
  }
}

async function clearLocation() {
  saving.value = true
  try {
    syncFromProfile(await updateProfile({ latitude: null, longitude: null, location_public: 0 }))
    ElMessage.success('位置已清除')
  } catch {
    ElMessage.error('清除失败，请稍后再试')
  } finally {
    saving.value = false
  }
}

onMounted(loadProfile)
</script>
