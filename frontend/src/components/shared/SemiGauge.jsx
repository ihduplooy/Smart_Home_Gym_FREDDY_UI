import { Box, Text, VStack } from '@chakra-ui/react'

// Reusable semicircular speedometer -- GYM's Constant panel (rep speed) is
// the first user, built here as a shared component rather than inline since
// a needle gauge with colored zones is generic enough other panels/tabs
// could reuse it later. Plain SVG (an arc path per zone + a needle line),
// not recharts' RadialBarChart -- a half-donut with a needle overlay isn't
// something RadialBarChart draws directly, and this is simpler than fighting
// it into that shape.
//
// Zone boundaries are a prop, not hardcoded here -- GYM's own zones (too
// slow / target / too fast) come from a config value (GymProfileEditor's rep
// speed target range), so retuning that doesn't mean touching this file.

const START_ANGLE_DEG = 180 // left end of the semicircle
const END_ANGLE_DEG = 0 // right end

function polarToCartesian(cx, cy, r, angleDeg) {
  const angleRad = (angleDeg * Math.PI) / 180
  return { x: cx + r * Math.cos(angleRad), y: cy - r * Math.sin(angleRad) }
}

function describeArc(cx, cy, r, startAngleDeg, endAngleDeg) {
  const start = polarToCartesian(cx, cy, r, startAngleDeg)
  const end = polarToCartesian(cx, cy, r, endAngleDeg)
  const largeArcFlag = Math.abs(startAngleDeg - endAngleDeg) <= 180 ? 0 : 1
  // sweep-flag=1: our points are generated with y = cy - r*sin(angle), so as
  // the angle DECREASES (180 -> 90 -> 0, our whole traversal direction --
  // left -> top -> right), the point moves in the positive-angle/clockwise
  // direction SVG's sweep-flag=1 means. sweep-flag=0 (the original bug) told
  // SVG to draw the *other* candidate circle -- the one mirrored across the
  // chord -- instead of the one these points actually lie on, which is what
  // produced disconnected "tent" spikes per zone instead of one smooth dome.
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArcFlag} 1 ${end.x} ${end.y}`
}

function valueToAngle(value, min, max) {
  const clamped = Math.min(Math.max(value, min), max)
  const fraction = max > min ? (clamped - min) / (max - min) : 0
  return START_ANGLE_DEG + fraction * (END_ANGLE_DEG - START_ANGLE_DEG)
}

/**
 * value/min/max: gauge range. zones: [{ from, to, color }] in value units,
 * covering [min, max] (gaps render as unfilled track). unit/label: readout
 * text under the arc.
 */
const SemiGauge = ({ value, min, max, zones = [], unit = '', label = '', size = 180 }) => {
  const cx = size / 2
  const cy = size / 2
  const r = size / 2 - 14
  const needleAngle = valueToAngle(value ?? min, min, max)
  const needleTip = polarToCartesian(cx, cy, r - 10, needleAngle)

  return (
    <VStack spacing={1} align="center">
      <Box position="relative" w={`${size}px`} h={`${size / 2 + 16}px`}>
        <svg width={size} height={size / 2 + 16} viewBox={`0 0 ${size} ${size / 2 + 16}`}>
          <path
            d={describeArc(cx, cy, r, START_ANGLE_DEG, END_ANGLE_DEG)}
            fill="none"
            stroke="#E4E4E7"
            strokeWidth={10}
            strokeLinecap="round"
          />
          {zones.map((zone, i) => (
            <path
              key={i}
              d={describeArc(cx, cy, r, valueToAngle(zone.from, min, max), valueToAngle(zone.to, min, max))}
              fill="none"
              stroke={zone.color}
              strokeWidth={10}
              strokeLinecap="butt"
              opacity={0.85}
            />
          ))}
          <line x1={cx} y1={cy} x2={needleTip.x} y2={needleTip.y} stroke="#18181B" strokeWidth={3} strokeLinecap="round" />
          <circle cx={cx} cy={cy} r={5} fill="#18181B" />
        </svg>
      </Box>
      <Text fontSize="lg" fontFamily="mono" fontWeight="semibold" color="paper.textPrimary" mt={-2}>
        {value != null ? value.toFixed(2) : '—'} <Text as="span" fontSize="xs" color="paper.textSecondary">{unit}</Text>
      </Text>
      {label && <Text fontSize="xs" color="paper.textSecondary">{label}</Text>}
    </VStack>
  )
}

export default SemiGauge
