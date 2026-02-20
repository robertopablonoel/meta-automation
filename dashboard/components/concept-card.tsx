"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import type { Concept } from "@/lib/types";

export function ConceptCard({ concept }: { concept: Concept }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">
          {concept.display_name || concept.name}
        </CardTitle>
        <CardDescription>{concept.name}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {concept.description && (
          <div>
            <h4 className="text-xs font-medium text-muted-foreground mb-1">
              Strategic Purpose
            </h4>
            <p className="text-sm">{concept.description}</p>
          </div>
        )}
        <Separator />
        <div className="space-y-3">
          {concept.schwartz_sophistication && (
            <div>
              <h4 className="text-xs font-medium text-muted-foreground mb-1">
                Awareness Stage
              </h4>
              <Badge variant="outline" className="text-xs whitespace-normal text-left">
                {concept.schwartz_sophistication}
              </Badge>
            </div>
          )}
          {concept.belief_mapping && (
            <div>
              <h4 className="text-xs font-medium text-muted-foreground mb-1">
                Belief Mapping
              </h4>
              <p className="text-xs leading-relaxed">{concept.belief_mapping}</p>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
