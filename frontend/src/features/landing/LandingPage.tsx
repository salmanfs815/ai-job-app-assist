import { ArrowRight, FileText, Gauge, LogIn, ShieldCheck, Sparkles } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/features/auth/auth-context";

function Feature({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="mb-2 flex size-10 items-center justify-center rounded-lg bg-accent text-accent-foreground [&_svg]:size-5">
          {icon}
        </div>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-pretty text-muted-foreground">{children}</CardContent>
    </Card>
  );
}

const STEPS = [
  { title: "Add your resume", body: "Upload a PDF or DOCX (scans are read with OCR) or paste the text." },
  { title: "Add the job description", body: "Paste the posting or upload it. You can edit the extracted text." },
  {
    title: "Get tailored output",
    body: "A match score with specific rewrites, or a cover letter, streamed as it is written.",
  },
];

export function LandingPage() {
  const { status, canSignIn, signIn } = useAuth();
  const signedIn = status === "signedIn";

  return (
    <div className="space-y-12 sm:space-y-16">
      <section className="space-y-6 pt-4 text-center sm:pt-10">
        <p className="mx-auto inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-sm text-muted-foreground">
          <Sparkles aria-hidden="true" className="size-4 text-primary" />
          Try it without an account
        </p>
        <h1 className="mx-auto max-w-3xl text-3xl font-bold tracking-tight text-balance sm:text-5xl">
          Tailor your resume to the job, not the other way round
        </h1>
        <p className="mx-auto max-w-2xl text-base text-pretty text-muted-foreground sm:text-lg">
          Compare your resume with a job description and get a candid match score, specific rewrites that never invent
          experience, and a cover letter draft.
        </p>
        <div className="flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Button asChild size="lg">
            <Link to="/analyze">
              Analyze a resume <ArrowRight aria-hidden="true" />
            </Link>
          </Button>
          {canSignIn && !signedIn ? (
            <Button size="lg" variant="outline" onClick={() => void signIn()} disabled={status === "loading"}>
              <LogIn aria-hidden="true" /> Sign in to save resumes
            </Button>
          ) : null}
          {signedIn ? (
            <Button asChild size="lg" variant="outline">
              <Link to="/resumes">Your saved resumes</Link>
            </Button>
          ) : null}
        </div>
      </section>

      <section aria-labelledby="how-heading" className="space-y-4">
        <h2 id="how-heading" className="text-xl font-semibold">
          How it works
        </h2>
        <ol className="grid gap-4 sm:grid-cols-3">
          {STEPS.map((step, index) => (
            <li key={step.title} className="rounded-xl border bg-card p-5">
              <span
                aria-hidden="true"
                className="mb-3 flex size-8 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground"
              >
                {index + 1}
              </span>
              <h3 className="font-medium">{step.title}</h3>
              <p className="mt-1 text-sm text-pretty text-muted-foreground">{step.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="features-heading" className="space-y-4">
        <h2 id="features-heading" className="text-xl font-semibold">
          What you get
        </h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <Feature icon={<FileText aria-hidden="true" />} title="Saved resumes">
            Keep several versions of your resume, pick a default, and reuse them without uploading again. Only the
            extracted text is stored, never the file.
          </Feature>
          <Feature icon={<Gauge aria-hidden="true" />} title="Fair-use limits">
            Guests get a few free generations a day and signed-in users get more. When a limit is reached the app says
            so and tells you when it resets.
          </Feature>
          <Feature icon={<ShieldCheck aria-hidden="true" />} title="Your data, your call">
            Guest results are never stored. If you sign in, you can delete your account and everything saved with it
            from the settings page.
          </Feature>
        </div>
      </section>
    </div>
  );
}
