/**
 * 首页 mock 数据
 * 主题：绿色社区 / 旧物改造 / 二手书籍 / 邻里交换（图片来自 Unsplash）
 */

// Unsplash 图片统一参数：自动格式、居中裁剪、压缩
const u = (id, w = 1920) =>
  `https://images.unsplash.com/${id}?auto=format&fit=crop&w=${w}&q=80`

/* ---------- Hero 全屏轮播（4 张） ---------- */
export const heroSlides = [
  {
    id: 1,
    theme: '绿色社区',
    image: u('photo-1466692476868-aef1dfb1e735'),
    thumb: u('photo-1466692476868-aef1dfb1e735', 320),
  },
  {
    id: 2,
    theme: '旧物改造',
    image: u('photo-1558618666-fcd25c85cd64'),
    thumb: u('photo-1558618666-fcd25c85cd64', 320),
  },
  {
    id: 3,
    theme: '二手书籍',
    image: u('photo-1507842217343-583bb7270b66'),
    thumb: u('photo-1507842217343-583bb7270b66', 320),
  },
  {
    id: 4,
    theme: '邻里交换',
    image: u('photo-1555529669-e69e7aa0ba9a'),
    thumb: u('photo-1555529669-e69e7aa0ba9a', 320),
  },
]

/* ---------- 低碳数据看板（4 项） ---------- */
export const lowCarbonStats = [
  { id: 1, label: '累计减碳量', value: 1250, suffix: 'kg' },
  { id: 2, label: '成功互换', value: 486, suffix: '次' },
  { id: 3, label: '注册用户', value: 320, suffix: '人' },
  { id: 4, label: '覆盖社区', value: 12, suffix: '个' },
]

/* ---------- 物品分类快捷入口（ID 对齐后端真实分类） ---------- */
export const categories = [
  { id: 22, name: '家电', icon: '🔌' },
  { id: 23, name: '母婴', icon: '🍼' },
  { id: 9, name: '图书', icon: '📚' },
  { id: 12, name: '家具', icon: '🪑' },
  { id: 21, name: '数码', icon: '📱' },
  { id: 13, name: '服饰', icon: '👕' },
  { id: 14, name: '运动', icon: '⚽' },
  { id: 24, name: '其他', icon: '🌿' },
]

/* ---------- 社区闲置物品：已迁移至 src/mock/items.js ---------- */

/* ---------- 邻里互换故事（3 个） ---------- */
export const swapStories = [
  {
    id: 1,
    name: '林阿姨',
    text: '把孙子小时候的绘本送给了楼下新搬来的年轻妈妈，她回赠我一盆绿萝。书有人读，花有人养，这就是邻里最好的样子。',
  },
  {
    id: 2,
    name: '阿杰',
    text: '用闲置的咖啡机换到了同小区的公路车头盔，线上约好周末广场交接，比二手平台省心多了，还多认识了一个骑友。',
  },
  {
    id: 3,
    name: '小满妈妈',
    text: '宝宝长得快，婴儿车、摇椅几乎没用几次。在社区里一件件流转出去，每次交接都觉得这些东西在替我们继续陪伴新的家庭。',
  },
]
