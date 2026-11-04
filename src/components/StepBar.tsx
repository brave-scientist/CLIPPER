import React from 'react';
import { Step } from '../types';
import { ChevronRight } from 'lucide-react';

interface StepBarProps {
  currentStep: Step;
  onSelectStep: (step: Step) => void;
}

const steps: { id: Step; label: string; number: number }[] = [
  { id: 'add', label: 'Add', number: 1 },
  { id: 'pick', label: 'Pick', number: 2 },
  { id: 'save', label: 'Save', number: 3 },
];

export const StepBar: React.FC<StepBarProps> = ({ currentStep, onSelectStep }) => {
  const currentIndex = steps.findIndex((s) => s.id === currentStep);

  return (
    <nav aria-label="Steps" className="w-full max-w-md mx-auto py-4 px-4">
      <div className="flex items-center justify-between">
        {steps.map((step, idx) => {
          const isActive = step.id === currentStep;
          const isDone = idx < currentIndex;

          return (
            <React.Fragment key={step.id}>
              <button
                onClick={() => onSelectStep(step.id)}
                className={`flex items-center gap-2 text-base font-bold transition-colors cursor-pointer py-1 px-2 rounded-lg ${
                  isActive
                    ? 'text-blue-600'
                    : isDone
                    ? 'text-slate-700 hover:text-blue-600'
                    : 'text-slate-400 hover:text-slate-600'
                }`}
              >
                <span
                  className={`w-7 h-7 rounded-full flex items-center justify-center text-sm font-black transition-colors ${
                    isActive
                      ? 'bg-blue-600 text-white shadow-sm'
                      : isDone
                      ? 'bg-blue-100 text-blue-700'
                      : 'bg-slate-100 text-slate-400'
                  }`}
                >
                  {step.number}
                </span>
                <span>{step.label}</span>
              </button>

              {idx < steps.length - 1 && (
                <ChevronRight className="w-4 h-4 text-slate-300 shrink-0" />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </nav>
  );
};
