
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
  // 本集文生视频(T2V)的默认画幅，由新建表单维护；点击“生成”时附加到 extra
  const [aspectRatio, setAspectRatio] = useState<string>('16:9')
  const [form] = Form.useForm()

  const load = async () => {
    if (!episodeId) return
    setShots(await listShots(episodeId))
  }
  useEffect(() => { load() }, [episodeId])

  const onAdd = async () => {
    const v = await form.validateFields()
    // aspect_ratio 只用于 T2V，不入库；从 payload 中剥离
    const { aspect_ratio, ...shotPayload } = v
    if (aspect_ratio) setAspectRatio(aspect_ratio)
    await createShot({ episode_id: episodeId, index: shots.length, ...shotPayload })
    message.success('已添加分镜')
    form.resetFields()
    await load()
  }

  const onGenerate = async (s: Shot) => {
    const isT2V = !s.image_url
    if (isT2V) {
      message.info({ content: `未设置首帧图，将走文生视频 (T2V ${aspectRatio})`, key: s.id })
    } else {
      message.loading({ content: '生成中...', key: s.id })
    }
    try {
      await generateShot({
        shot_id: s.id,
        backend: s.model_backend || 'hailuo',
        // T2V 需要显式比例，有首帧图时后端会忽略
        extra: isT2V ? { aspect_ratio: aspectRatio } : undefined,
      })
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
              <Form.Item
                name="aspect_ratio"
                label="宽高比 (T2V)"
                initialValue={aspectRatio}
                tooltip="未设置首帧图时的文生视频画幅；若设置了首帧图则由图片决定"
              >
                <Select
                  onChange={(v) => setAspectRatio(v)}
                  options={[
                    { value: '16:9', label: '16:9 横屏' },
                    { value: '9:16', label: '9:16 竖屏' },
                    { value: '1:1', label: '1:1 方形' },
                    { value: '4:3', label: '4:3' },
                    { value: '3:4', label: '3:4' },
                    { value: '21:9', label: '21:9 影院' },
                    { value: 'adaptive', label: '自适应' },
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
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={<span style={{ fontSize: 12 }}>无首帧图 · 将走文生视频</span>}
                />
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
