'use client'
import { AssessmentDetail } from '@/components/shared/AssessmentWorkspace'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'

export function ResultsView({ assessmentId, onBackToCreate }: { assessmentId: string | null; onBackToCreate: () => void }) {
  if (assessmentId) return <AssessmentDetail key={assessmentId} id={assessmentId} onBack={onBackToCreate} />
  return <Card className="max-w-3xl mx-auto"><p className="text-text-2">Generate a quiz to review its draft, or open a saved draft from Assessments.</p><Button className="mt-4" onClick={onBackToCreate}>Go to Create</Button></Card>
}
