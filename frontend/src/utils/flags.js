const ENGLAND_FLAG_TAG = '\u{1F3F4}\u{E0067}\u{E0062}\u{E0065}\u{E006E}\u{E0067}\u{E007F}'
const SCOTLAND_FLAG_TAG = '\u{1F3F4}\u{E0067}\u{E0062}\u{E0073}\u{E0063}\u{E0074}\u{E007F}'

const normalize = (value) => (
  String(value || '')
    .trim()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
)

const hasTeamMarker = (values, markers) => (
  values.some(value => markers.includes(normalize(value)))
)

export const getFlagUrl = (flagIcon, team = {}) => {
  const values = [
    flagIcon,
    team?.fifa_code,
    team?.name,
    team?.team_name,
    team?.team1_name,
    team?.team2_name
  ].filter(Boolean)

  if (
    flagIcon === ENGLAND_FLAG_TAG ||
    hasTeamMarker(values, ['eng', 'england', 'inglaterra'])
  ) {
    return 'https://flagcdn.com/w40/gb-eng.png'
  }

  if (
    flagIcon === SCOTLAND_FLAG_TAG ||
    hasTeamMarker(values, ['sco', 'scotland', 'escocia'])
  ) {
    return 'https://flagcdn.com/w40/gb-sct.png'
  }

  if (!flagIcon || flagIcon === '🏳️') return null

  const codePoints = Array.from(flagIcon).map(char => char.codePointAt(0))
  if (codePoints.length >= 2 && codePoints[0] >= 127462 && codePoints[0] <= 127487) {
    const char1 = String.fromCharCode(codePoints[0] - 127397)
    const char2 = String.fromCharCode(codePoints[1] - 127397)
    return `https://flagcdn.com/w40/${(char1 + char2).toLowerCase()}.png`
  }
  return null
}
