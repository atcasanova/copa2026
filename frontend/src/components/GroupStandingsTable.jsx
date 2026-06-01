import React from 'react'
import {
  Box, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Paper, Typography, Tooltip
} from '@mui/material'
import { HelpOutline } from '@mui/icons-material'
import { getFlagUrl } from '../utils/flags'

export default function GroupStandingsTable({ standings = [], dense = false }) {
  return (
    <TableContainer component={Paper} sx={{ boxShadow: 'none', borderRadius: 2 }}>
      <Table size={dense ? 'small' : 'medium'}>
        <TableHead>
          <TableRow>
            <TableCell sx={{ width: 42 }}>#</TableCell>
            <TableCell>Seleção</TableCell>
            <TableCell align="center">Pts</TableCell>
            <TableCell align="center">J</TableCell>
            <TableCell align="center">V</TableCell>
            <TableCell align="center">E</TableCell>
            <TableCell align="center">D</TableCell>
            <TableCell align="center">GP</TableCell>
            <TableCell align="center">SG</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {standings.map((row, idx) => {
            const flagUrl = getFlagUrl(row.flag_icon, row)
            return (
              <TableRow key={row.name}>
                <TableCell sx={{ fontWeight: 800 }}>{idx + 1}</TableCell>
                <TableCell>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    {flagUrl ? (
                      <img src={flagUrl} alt="" style={{ width: 22, height: 15, borderRadius: 2, objectFit: 'cover' }} />
                    ) : (
                      <span>{row.flag_icon}</span>
                    )}
                    <Typography variant="body2" sx={{ fontWeight: 700 }}>
                      {row.fifa_code || row.name}
                    </Typography>
                  </Box>
                </TableCell>
                <TableCell align="center" sx={{ fontWeight: 800, color: 'primary.light' }}>{row.points}</TableCell>
                <TableCell align="center">{row.played}</TableCell>
                <TableCell align="center">{row.wins}</TableCell>
                <TableCell align="center">{row.draws}</TableCell>
                <TableCell align="center">{row.losses}</TableCell>
                <TableCell align="center">{row.goals_for}</TableCell>
                <TableCell align="center" sx={{ fontWeight: 700 }}>{row.goal_difference}</TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
      <Box sx={{ px: 2, py: 1, display: 'flex', alignItems: 'center', gap: 0.5 }}>
        <Typography variant="caption" color="text.secondary">
          Critérios FIFA: pontos, saldo, gols pró e confronto direto.
        </Typography>
        <Tooltip title="Sem dados de fair play ou sorteio; nesses casos o sistema usa ordem alfabética como último critério.">
          <HelpOutline sx={{ fontSize: '0.85rem', color: 'text.secondary', cursor: 'help' }} />
        </Tooltip>
      </Box>
    </TableContainer>
  )
}
