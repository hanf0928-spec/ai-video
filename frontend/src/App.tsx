
import { Layout, Menu } from 'antd'
import {
  AppstoreOutlined, FileImageOutlined, PictureOutlined,
  TeamOutlined, SettingOutlined, PlaySquareOutlined, ApiOutlined,
} from '@ant-design/icons'
import { Routes, Route, useNavigate, useLocation, Navigate } from 'react-router-dom'
import ProjectsPage from './pages/ProjectsPage'
import ProjectDetailPage from './pages/ProjectDetailPage'
import Manga2AnimePage from './pages/Manga2AnimePage'
import StoryboardPage from './pages/StoryboardPage'
import CharactersPage from './pages/CharactersPage'
import JobsPage from './pages/JobsPage'
import SettingsPage from './pages/SettingsPage'
import ModelConfigPage from './pages/ModelConfigPage'

const { Header, Sider, Content } = Layout

export default function App() {
  const nav = useNavigate()
  const loc = useLocation()

  const selectedKey =
    loc.pathname.startsWith('/manga2anime') ? 'm2a' :
    loc.pathname.startsWith('/storyboard') ? 'sb' :
    loc.pathname.startsWith('/characters') ? 'ch' :
    loc.pathname.startsWith('/jobs') ? 'jb' :
    loc.pathname.startsWith('/models') ? 'mc' :
    loc.pathname.startsWith('/settings') ? 'st' : 'pj'

  return (
    <Layout className="app-layout" style={{ minHeight: '100vh' }}>
      <Sider width={220}>
        <div className="app-logo">🎬 AI 漫剧工作流</div>
        <Menu
          mode="inline"
          theme="dark"
          selectedKeys={[selectedKey]}
          onClick={(e) => {
            const map: any = {
              pj: '/projects', m2a: '/manga2anime', sb: '/storyboard',
              ch: '/characters', jb: '/jobs', mc: '/models', st: '/settings',
            }
            nav(map[e.key])
          }}
          items={[
            { key: 'pj', icon: <AppstoreOutlined />, label: '项目' },
            { key: 'm2a', icon: <FileImageOutlined />, label: '漫画转漫剧' },
            { key: 'sb', icon: <PictureOutlined />, label: '分镜工作台' },
            { key: 'ch', icon: <TeamOutlined />, label: '角色与场景' },
            { key: 'jb', icon: <PlaySquareOutlined />, label: '任务队列' },
            { key: 'mc', icon: <ApiOutlined />, label: '模型配置' },
            { key: 'st', icon: <SettingOutlined />, label: '设置' },
          ]}
        />
      </Sider>
      <Layout>
        <Header><span style={{ color: '#fff' }}>AI Manga-to-Anime Studio</span></Header>
        <Content style={{ padding: 24 }}>
          <Routes>
            <Route path="/" element={<Navigate to="/projects" replace />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/projects/:id" element={<ProjectDetailPage />} />
            <Route path="/manga2anime" element={<Manga2AnimePage />} />
            <Route path="/storyboard" element={<StoryboardPage />} />
            <Route path="/storyboard/:episodeId" element={<StoryboardPage />} />
            <Route path="/characters" element={<CharactersPage />} />
            <Route path="/jobs" element={<JobsPage />} />
            <Route path="/models" element={<ModelConfigPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  )
}
