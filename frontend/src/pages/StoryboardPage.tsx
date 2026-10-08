
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  Button, Card, Col, Empty, Form, Input, InputNumber, Row, Select, Space, Tag, Typography, message,
} from 'antd'
import { PlayCircleOutlined, PlusOutlined } from '@ant-design/icons'
import { listShots, createShot, updateShot, generateShot } from '../api'
import type { Shot } from '../types'

const { Title } = Typography

export default function StoryboardPage() {
  const { episodeId } = useParams()
  const [shots, setShots] = useState<Shot[]>([])
  const [form] = Form.useForm()

  const load = async () => {
    if (!episodeId) return
    setShots(await listShots(episodeId))
  }
  useEffect(() => { load() }, [episodeId])

  const onAdd = async () => {
    const v = await form.validateFields()
    await createShot({ episode_id: episodeId, index: shots.length, ...v })
    message.success('已添加分镜')
    form.resetFields()
    await load()
  }

  const onGenerate = async (s: Shot) => {
    if (!s.image_url) { message.warning('请先设置首帧图'); return }
    message.loading({ content: '生成中...', key: s.id })
    try {
      await generateShot({ shot_id: s.id, backend: s.model_backend || 'hailuo' })
      message.success({ content: '生成完成', key: s.id })
      await load()
    } catch (e: any) {
      message.error({ content: e.message, key: s.id })
    }
  }

  if (!episodeId) {
    return (
      <Empty description="请先从项目中选择一个剧集" />
    )
  }

  return (
    <div>
      <Title level={3} style={{ color: '#fff' }}>📝 分镜工作台</Title>

      <Card title="➕ 新建分镜" style={{ marginBottom: 16 }}>
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={16}>
              <Form.Item name="prompt" label="场景描述 (Prompt)" rules={[{ required: true }]}>
                <Input.TextArea rows={2} placeholder="日系动画，少女在樱花树下微笑，电影感构图" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="duration" label="时长(秒)" initialValue={4}>
                <InputNumber min={2} max={10} />
              </Form.Item>
              <Form.Item name="model_backend" label="模型" initialValue="hailuo">
                <Select
                  options={[
                    { value: 'hailuo', label: '海螺 03' },
                    { value: 'seedance', label: 'Seedance 2' },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="dialogue" label="对白">
            <Input placeholder="（可留空）" />
          </Form.Item>
          <Button type="primary" icon={<PlusOutlined />} onClick={onAdd}>添加</Button>
        </Form>
      </Card>

      <div className="card-grid">
        {shots.map((s) => (
          <Card
            key={s.id}
            size="small"
            title={<span>#{s.index + 1} <Tag>{s.model_backend}</Tag></span>}
            extra={<Tag color={s.status === 'done' ? 'green' : 'default'}>{s.status}</Tag>}
            actions={[
              <Button type="link" icon={<PlayCircleOutlined />} onClick={() => onGenerate(s)}>生成</Button>,
            ]}
          >
            <div style={{ minHeight: 100 }}>
              {s.image_url ? (
                <img src={`/static/outputs/${s.image_url.split('/outputs/')[1]}`} alt=""
                     style={{ width: '100%', borderRadius: 6 }} />
              ) : (
                <Empty description="无首帧图" />
              )}
            </div>
            <p style={{ marginTop: 8, fontSize: 12 }}>{s.prompt}</p>
            {s.dialogue && <p style={{ fontSize: 12, color: '#8b5cf6' }}>💬 {s.dialogue}</p>}
            {s.video_url && (
              <video src={`/static/outputs/${s.video_url.split('/outputs/')[1]}`}
                     controls style={{ width: '100%' }} />
            )}
          </Card>
        ))}
      </div>
    </div>
  )
}
