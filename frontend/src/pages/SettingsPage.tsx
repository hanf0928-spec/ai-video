
import { useEffect, useState } from 'react'
import { Card, Tag, Typography, Button, Space, Divider, Alert } from 'antd'
import { CheckCircleFilled, CloseCircleFilled, ReloadOutlined, ApiOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { comfyHealth, listWorkflows } from '../api'

const { Title, Paragraph, Text } = Typography

export default function SettingsPage() {
  const [comfyOk, setComfyOk] = useState(false)
  const [workflows, setWorkflows] = useState<string[]>([])
  const nav = useNavigate()

  const check = async () => {
    try {
      const r = await comfyHealth()
      setComfyOk(!!r.success)
    } catch { setComfyOk(false) }
    try {
      const r = await listWorkflows()
      setWorkflows(r.data || [])
    } catch {}
  }
  useEffect(() => { check() }, [])

  return (
    <div style={{ maxWidth: 900 }}>
      <Title level={3} style={{ color: '#fff' }}>⚙️ 系统设置</Title>

      <Card title="组件状态" extra={<Button size="small" icon={<ReloadOutlined />} onClick={check}>刷新</Button>}>
        <Space direction="vertical">
          <Text>
            {comfyOk ? <CheckCircleFilled style={{ color: '#52c41a' }} /> : <CloseCircleFilled style={{ color: '#ff4d4f' }} />}
            {' '}ComfyUI 服务 {comfyOk ? '在线' : '离线'}
          </Text>
        </Space>
      </Card>

      <Card title="工作流列表" style={{ marginTop: 16 }}>
        {workflows.length === 0 ? (
          <Text type="secondary">暂无工作流</Text>
        ) : workflows.map((w) => <Tag key={w} color="purple" style={{ margin: 4 }}>{w}</Tag>)}
      </Card>

      <Card title="模型接入" style={{ marginTop: 16 }}>
        <Alert
          type="info"
          showIcon
          message="所有模型 API Key / Endpoint 现在统一通过控制台配置"
          description="海螺03、Seedance2、LLM、TTS、ComfyUI 等的接入信息请前往「模型配置」页填写并测试连接。"
        />
        <Divider />
        <Button type="primary" icon={<ApiOutlined />} onClick={() => nav('/models')}>
          前往模型配置
        </Button>
      </Card>

      <Card title=".env 配置项" style={{ marginTop: 16 }}>
        <Paragraph>
          <b>仅应用级配置</b>（存储路径、Redis、CORS、OCR 等）保留在 <code>.env</code>，
          修改后需要重启后端生效。
        </Paragraph>
        <Paragraph>
          <Text type="warning">⚠️ 注意：APP_SECRET_KEY 用于加密模型配置中的 API Key，</Text>
          <Text type="warning">一旦修改需要重新填写模型配置页中的所有敏感字段。</Text>
        </Paragraph>
      </Card>
    </div>
  )
}
