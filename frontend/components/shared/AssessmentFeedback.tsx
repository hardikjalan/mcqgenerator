'use client'

import type { Feedback, Accuracy } from '@/types/assessment'
import type { Evidence } from '@/types/quiz'
import { Card, CardHeader } from '@/components/ui/Card'

export function SourceQuote({ source }: { source: Evidence }) {
  const pages = source.pages?.length ? source.pages.join(', ') : source.page
  return <blockquote className="border-l-2 border-accent-line pl-3 py-1 text-sm text-text-2">
    <p className="whitespace-pre-wrap">“{source.quote}”</p>
    <footer className="mt-1 text-xs text-text-3">{source.file_name}{pages ? ` · Page/slide ${pages}` : ''}</footer>
  </blockquote>
}

export function AccuracyTable({ values, label }: { values: Record<string, Accuracy>; label: string }) {
  return <div className="overflow-x-auto"><table className="w-full text-sm text-left">
    <thead><tr className="border-b border-border-strong text-text-3"><th className="py-2 pr-3">{label}</th><th className="py-2 pr-3">Correct</th><th className="py-2">Accuracy</th></tr></thead>
    <tbody>{Object.entries(values).map(([name, value]) => <tr key={name} className="border-b border-border-subtle">
      <th className="py-3 pr-3 font-medium text-text">{name}</th><td className="pr-3 tabular">{value.correct}/{value.total}</td>
      <td className="tabular">{value.total ? Math.round(100 * value.correct / value.total) : 0}%</td>
    </tr>)}</tbody>
  </table>{Object.keys(values).length === 0 && <p className="py-4 text-text-3">No responses yet.</p>}</div>
}

export function AssessmentFeedback({ feedback }: { feedback: Feedback }) {
  return <div className="flex flex-col gap-5">
    <Card><CardHeader title="Your topics" /><AccuracyTable values={feedback.topics} label="Topic" /></Card>
    <Card><CardHeader title="Estimated mastery" hint={feedback.mastery_method} />
      <div className="flex flex-col gap-4">{Object.entries(feedback.mastery).map(([topic, estimate]) => <div key={topic}>
        <div className="flex justify-between gap-3 text-sm mb-1"><span>{topic}</span><span className="tabular">{Math.round(100 * estimate.probability)}% · {estimate.observations} observations</span></div>
        <progress className="w-full accent-accent" value={estimate.probability} max={1} aria-label={`Estimated mastery of ${topic}`} />
      </div>)}{!Object.keys(feedback.mastery).length && <p className="text-sm text-text-3">Answer questions to build a mastery estimate.</p>}</div>
    </Card>
    <Card><CardHeader title="What to work on next" />
      {feedback.recommendations.length ? <div className="flex flex-col gap-5">{feedback.recommendations.map(item => <section key={item.topic} className="flex flex-col gap-2">
        <h3 className="text-base font-semibold">{item.topic}</h3><p className="text-sm text-text-2">{item.message}</p>
        {item.sources.map((source, i) => <SourceQuote key={i} source={source} />)}
      </section>)}</div> : <p className="text-sm text-text-2">You met the 70% accuracy target across these topics. Try harder application and analysis questions next.</p>}
    </Card>
    <Card><CardHeader title="Answer review" />
      <div className="flex flex-col gap-4">{feedback.questions.map((question, i) => <details key={question.id} className="border border-border-strong rounded-md p-3">
        <summary className="cursor-pointer text-base font-semibold">{i + 1}. {question.question} <span className={question.correct ? 'text-success' : 'text-danger'}>({question.correct ? 'Correct' : question.selected.length ? 'Incorrect' : 'Unanswered'})</span></summary>
        <div className="flex flex-col gap-3 mt-3 text-sm">
          <p>Your answer: {question.selected.map(index => question.options[index]).join('; ') || 'Not answered'}</p>
          <p className="text-success">Correct answer: {Array.isArray(question.correct_answer) ? question.correct_answer.join('; ') : question.correct_answer}</p>
          <p className="text-text-2">{question.explanation}</p>
          <p className="text-xs text-text-3">{question.bloom_level} · Difficulty {question.difficulty}/5 · {question.bloom_rationale}</p>
          {question.evidence.map((source, index) => <SourceQuote key={index} source={source} />)}
        </div>
      </details>)}</div>
    </Card>
  </div>
}
