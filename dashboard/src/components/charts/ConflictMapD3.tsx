import { useEffect, useRef } from 'react'
import * as d3 from 'd3'
import type { ConflictResponse } from '@/types'

interface Node {
  id: string
  name: string
  x?: number
  y?: number
  fx?: number | null
  fy?: number | null
}

interface Link {
  source: string | Node
  target: string | Node
  severity: string
}

interface ConflictMapProps {
  conflicts: ConflictResponse[]
  width?: number
  height?: number
}

const SEVERITY_LINK_COLOR: Record<string, string> = {
  CRITICAL: '#ef4444',
  HIGH:     '#f97316',
  MEDIUM:   '#f59e0b',
  LOW:      '#22c55e',
}

export function ConflictMapD3({ conflicts, width = 600, height = 400 }: ConflictMapProps) {
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    if (!svgRef.current || conflicts.length === 0) return

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    // Build unique nodes + links from conflicts
    const nodeMap = new Map<string, Node>()
    conflicts.forEach((c) => {
      if (!nodeMap.has(c.toolAId)) nodeMap.set(c.toolAId, { id: c.toolAId, name: c.toolAName })
      if (!nodeMap.has(c.toolBId)) nodeMap.set(c.toolBId, { id: c.toolBId, name: c.toolBName })
    })
    const nodes: Node[] = Array.from(nodeMap.values())
    const links: Link[] = conflicts.map((c) => ({
      source: c.toolAId,
      target: c.toolBId,
      severity: c.severity,
    }))

    // Container group with zoom
    const g = svg.append('g')
    svg.call(
      d3.zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.3, 3])
        .on('zoom', (event) => g.attr('transform', event.transform)),
    )

    // Force simulation
    const simulation = d3
      .forceSimulation<Node>(nodes)
      .force('link', d3.forceLink<Node, Link>(links).id((d) => d.id).distance(100))
      .force('charge', d3.forceManyBody().strength(-200))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide(28))

    // Links
    const link = g
      .append('g')
      .selectAll('line')
      .data(links)
      .enter()
      .append('line')
      .attr('stroke', (d) => SEVERITY_LINK_COLOR[d.severity] ?? '#9ca3af')
      .attr('stroke-width', (d) => d.severity === 'CRITICAL' ? 2.5 : 1.5)
      .attr('stroke-opacity', 0.7)
      .attr('stroke-dasharray', (d) => d.severity === 'CRITICAL' ? '' : '5,3')

    // Nodes
    const node = g
      .append('g')
      .selectAll<SVGGElement, Node>('g')
      .data(nodes)
      .enter()
      .append('g')
      .style('cursor', 'grab')
      .call(
        d3.drag<SVGGElement, Node>()
          .on('start', (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart()
            d.fx = d.x; d.fy = d.y
          })
          .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y })
          .on('end', (event, d) => {
            if (!event.active) simulation.alphaTarget(0)
            d.fx = null; d.fy = null
          }),
      )

    node.append('circle')
      .attr('r', 18)
      .attr('fill', '#eef2ff')
      .attr('stroke', '#6366f1')
      .attr('stroke-width', 1.5)

    node.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', '0.35em')
      .attr('font-size', 9)
      .attr('fill', '#4338ca')
      .attr('font-family', 'Inter, sans-serif')
      .text((d) => d.name.length > 12 ? d.name.slice(0, 11) + '…' : d.name)

    // Tooltip
    const tooltip = d3.select('body').append('div')
      .attr('class', 'mtgs-tooltip')
      .style('position', 'absolute')
      .style('background', 'white')
      .style('border', '1px solid #e5e7eb')
      .style('border-radius', '8px')
      .style('padding', '6px 10px')
      .style('font-size', '12px')
      .style('pointer-events', 'none')
      .style('opacity', 0)
      .style('z-index', 999)

    node
      .on('mouseover', (event, d) => {
        tooltip.transition().duration(150).style('opacity', 1)
        tooltip.html(`<strong>${d.name}</strong>`)
          .style('left', `${event.pageX + 12}px`)
          .style('top',  `${event.pageY - 28}px`)
      })
      .on('mousemove', (event) => {
        tooltip
          .style('left', `${event.pageX + 12}px`)
          .style('top',  `${event.pageY - 28}px`)
      })
      .on('mouseout', () => tooltip.transition().duration(150).style('opacity', 0))

    // Tick
    simulation.on('tick', () => {
      link
        .attr('x1', (d) => (d.source as Node).x ?? 0)
        .attr('y1', (d) => (d.source as Node).y ?? 0)
        .attr('x2', (d) => (d.target as Node).x ?? 0)
        .attr('y2', (d) => (d.target as Node).y ?? 0)

      node.attr('transform', (d) => `translate(${d.x ?? 0},${d.y ?? 0})`)
    })

    return () => {
      simulation.stop()
      tooltip.remove()
    }
  }, [conflicts, width, height])

  if (conflicts.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-gray-400">
        No conflicts to display
      </div>
    )
  }

  return (
    <svg
      ref={svgRef}
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="bg-gray-50 rounded-lg"
    />
  )
}
