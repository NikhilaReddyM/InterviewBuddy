export const DESIGN_SECTIONS = [
  { key: 'requirementsAndAssumptions', label: 'Requirements and assumptions', hint: 'Define users, core features, constraints, and what is out of scope.' },
  { key: 'scaleEstimates', label: 'Scale estimates', hint: 'Estimate traffic, storage, bandwidth, and peak load. State your assumptions.' },
  { key: 'apisAndDataModel', label: 'APIs and data model', hint: 'Sketch endpoints, entities, relationships, and access patterns.' },
  { key: 'architectureNotes', label: 'Architecture notes', hint: 'Describe components, data flow, storage choices, and dependencies.' },
  { key: 'tradeoffsAndFailureScenarios', label: 'Tradeoffs and failure scenarios', hint: 'Explain alternatives, bottlenecks, failure modes, and recovery.' },
  { key: 'missedAndNextSteps', label: 'What I missed and next steps', hint: 'Reflect on gaps and choose a concrete next practice step.' },
] as const

export const DESIGN_CHECKLIST = [
  { key: 'scalability', label: 'Scalability', hint: 'Can the design handle growth and hotspots?' },
  { key: 'reliability', label: 'Reliability', hint: 'What happens when components fail?' },
  { key: 'consistency', label: 'Consistency', hint: 'Which consistency guarantees are required?' },
  { key: 'security', label: 'Security', hint: 'How are access and sensitive data protected?' },
  { key: 'observability', label: 'Observability', hint: 'How will you detect and diagnose problems?' },
] as const
