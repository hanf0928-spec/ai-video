
import { useEffect, useState } from 'react'
import {
  Alert, Badge, Button, Card, Col, Collapse, Divider, Form, Input, InputNumber,
  Row, Space, Switch, Tag, Tooltip, Typography, message,
} from 'antd'
import {
  CheckCircleTwoTone, CloseCircleTwoTone, EyeInvisibleOutlined, EyeTwoTone,
  SaveOutlined, ThunderboltOutlined, ReloadOutlined,
} from '@ant-design/icons'
import { http } from '../api'

const { Title, Text, Paragraph } = Typography

type FieldMeta = { type: 'string' | 'int' | 'float'; secret: boolean; default: any; desc?: string }
type ProviderPublic = {
  provider: string
  enabled: boolean
  config: Record<string, any>
  schema: Record<string, FieldMeta>
  last_tested_at?: string | null
  last_test_ok?: boolean | null
  last_test_message?: string | null
}

const PROVIDER_LABEL: Record<string, { icon: string; name: string; desc: string }> = {
  hailuo:   { icon: '🎥', name: '海螺 03 (MiniMax)', desc: '图生视频云端 API' },
  seedance: { icon: '🎬', name: 'Seedance 2 (字节)', desc: '图生视频云端 API' },
  llm:      { icon: '🧠', name: 'LLM (OpenAI 兼容)', desc: '分镜脚本生成' },
  tts:      { icon: '🔊', name: 'TTS (MiniMax)',    desc: '角色配音合成' },
  comfyui:  { icon: '🎨', name: 'ComfyUI',          desc: '本地推理引擎（无需 Key）' },
}

export default function ModelConfigPage() {
  const [list, setList] = useState<ProviderPublic[]>([])
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const r = await http.get('/config/providers')
      setList(r.data?.data || [])
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { load() }, [])

  return (
    <div style={{ maxWidth: 1100 }}>
      <Space style={{ justifyContent: 'space-between', width: '100%', marginBottom: 12 }}>
        <Title level={3} style={{ color: '#fff', margin: 0 }}>🔧 模型配置</Title>
        <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>
      </Space>
      <Alert
        type="info" showIcon
        message="所有模型 API Key / Endpoint 在此处集中配置。敏感字段加密保存在数据库中，重启后仍然有效。"
        style={{ marginBottom: 16 }}
      />

      <Row gutter={[16, 16]}>
        {list.map((p) => (
          <Col xs={24} lg={12} key={p.provider}>
            <ProviderCard data={p} onSaved={load} />
          </Col>
        ))}
      </Row>
    </div>
  )
}


function ProviderCard({ data, onSaved }: { data: ProviderPublic; onSaved: () => void }) {
  const [form] = Form.useForm()
  const [enabled, setEnabled] = useState(data.enabled)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const info = PROVIDER_LABEL[data.provider] || { icon: '⚙️', name: data.provider, desc: '' }

  // 初始值：secret 字段留空（避免显示密文），其他字段显示现值
  useEffect(() => {
    const initial: Record<string, any> = {}
    for (const [field, meta] of Object.entries(data.schema)) {
      const current = data.config[field]
      if (meta.secret) {
        initial[field] = '' // 显示空，占位符会提示 masked
      } else {
        initial[field] = current ?? meta.default
      }
    }
    form.setFieldsValue(initial)
    setEnabled(data.enabled)
  }, [data])

  const onSave = async () => {
    try {
      const values = await form.validateFields()
      setSaving(true)
      // 删除空的 secret 字段（表示"保持原值"）
      const payload: Record<string, any> = {}
      for (const [field, meta] of Object.entries(data.schema)) {
        const v = values[field]
        if (meta.secret && (v === '' || v == null)) continue
        payload[field] = v
      }
      await http.put(`/config/providers/${data.provider}`, { enabled, config: payload })
      message.success(`${info.name} 已保存`)
      onSaved()
    } catch (e: any) {
      if (e?.errorFields) return
      message.error(e.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const onTest = async () => {
    setTesting(true)
    try {
      const r = await http.post(`/config/providers/${data.provider}/test`)
      if (r.data?.success) {
        message.success(r.data?.message || '连接成功')
      } else {
        message.error(r.data?.message || '连接失败')
      }
      onSaved()
    } finally {
      setTesting(false)
    }
  }

  const renderField = (field: string, meta: FieldMeta) => {
    const current = data.config[field]
    const hasValue = meta.secret ? !!(current && typeof current === 'object' && current.has_value) : current != null
    const masked = meta.secret && hasValue ? current.masked : ''

    const label = (
      <Space>
        <span>{field}</span>
        {meta.secret && <Tag color="volcano">secret</Tag>}
        {meta.desc && <Tooltip title={meta.desc}><Text type="secondary">?</Text></Tooltip>}
      </Space>
    )

    if (meta.type === 'int' || meta.type === 'float') {
      return (
        <Form.Item key={field} label={label} name={field}>
          <InputNumber style={{ width: '100%' }} step={meta.type === 'float' ? 0.1 : 1} />
        </Form.Item>
      )
    }

    if (meta.secret) {
      return (
        <Form.Item
          key={field}
          label={label}
          name={field}
          extra={hasValue ? <Text type="secondary">当前值：{masked}（留空则保持不变）</Text> : null}
        >
          <Input.Password
            placeholder={hasValue ? '保持原值' : '请填写'}
            iconRender={(v) => (v ? <EyeTwoTone /> : <EyeInvisibleOutlined />)}
            autoComplete="new-password"
          />
        </Form.Item>
      )
    }

    return (
      <Form.Item key={field} label={label} name={field}>
        <Input placeholder={String(meta.default ?? '')} />
      </Form.Item>
    )
  }

  const statusTag = data.last_test_ok === null || data.last_test_ok === undefined
    ? <Tag>未测试</Tag>
    : data.last_test_ok
      ? <Tag icon={<CheckCircleTwoTone twoToneColor="#52c41a" />} color="success">可用</Tag>
      : <Tag icon={<CloseCircleTwoTone twoToneColor="#ff4d4f" />} color="error">异常</Tag>

  return (
    <Card
      title={
        <Space>
          <span style={{ fontSize: 18 }}>{info.icon}</span>
          <span>{info.name}</span>
          {statusTag}
        </Space>
      }
      extra={
        <Space>
          <Text type="secondary" style={{ fontSize: 12 }}>启用</Text>
          <Switch checked={enabled} onChange={setEnabled} size="small" />
        </Space>
      }
    >
      <Paragraph type="secondary" style={{ marginTop: -8 }}>{info.desc}</Paragraph>

      <Form form={form} layout="vertical" size="small">
        {Object.entries(data.schema).map(([field, meta]) => renderField(field, meta))}
      </Form>

      {data.last_test_message && (
        <Alert
          type={data.last_test_ok ? 'success' : 'error'}
          message={data.last_test_message}
          style={{ marginBottom: 12 }}
          showIcon
        />
      )}

      <Divider style={{ margin: '12px 0' }} />
      <Space>
        <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={onSave}>保存</Button>
        <Button icon={<ThunderboltOutlined />} loading={testing} onClick={onTest}>测试连接</Button>
      </Space>
    </Card>
  )
}
