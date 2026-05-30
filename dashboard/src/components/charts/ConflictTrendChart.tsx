import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts'

// Mock trend data — replace with real API data when available
const MOCK_DATA = [
  { date: 'May 20', critical: 2, high: 5, medium: 8 },
  { date: 'May 21', critical: 3, high: 4, medium: 10 },
  { date: 'May 22', critical: 1, high: 6, medium: 7 },
  { date: 'May 23', critical: 4, high: 8, medium: 12 },
  { date: 'May 24', critical: 2, high: 5, medium: 9 },
  { date: 'May 25', critical: 3, high: 7, medium: 11 },
  { date: 'May 26', critical: 1, high: 4, medium: 8 },
]

export function ConflictTrendChart() {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={MOCK_DATA} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
        <defs>
          <linearGradient id="critical" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#ef4444" stopOpacity={0.15} />
            <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="high" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#f97316" stopOpacity={0.15} />
            <stop offset="95%" stopColor="#f97316" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="medium" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.15} />
            <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
        <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
        <Tooltip
          contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Area type="monotone" dataKey="critical" stroke="#ef4444" fill="url(#critical)" strokeWidth={2} dot={false} />
        <Area type="monotone" dataKey="high" stroke="#f97316" fill="url(#high)" strokeWidth={2} dot={false} />
        <Area type="monotone" dataKey="medium" stroke="#f59e0b" fill="url(#medium)" strokeWidth={2} dot={false} />
      </AreaChart>
    </ResponsiveContainer>
  )
}
