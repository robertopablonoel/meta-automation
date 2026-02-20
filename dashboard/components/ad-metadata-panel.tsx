"use client";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import type { AdDescription, CopyVariation, Concept } from "@/lib/types";

interface Props {
  description?: AdDescription | null;
  copyVariations?: CopyVariation[];
  concept?: Concept | null;
  subGroupName?: string;
}

export function AdMetadataPanel({
  description,
  copyVariations,
  concept,
  subGroupName,
}: Props) {
  const hasAnyData = description || (copyVariations && copyVariations.length > 0) || concept;

  if (!hasAnyData) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          No pipeline metadata available for this ad.
          <br />
          <span className="text-xs">Run the pipeline with --publish to populate.</span>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Ad Description */}
      {description && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Visual Analysis</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-4">
              <MetadataField
                label="Visual Elements"
                value={description.visual_elements}
              />
              <MetadataField
                label="Emotional Tone"
                value={description.emotional_tone}
              />
              <MetadataField
                label="Implied Message"
                value={description.implied_message}
              />
              <MetadataField
                label="Awareness Level"
                value={description.target_awareness_level}
              />
            </div>
            {description.transcript_summary && (
              <>
                <Separator />
                <MetadataField
                  label="Transcript Summary"
                  value={description.transcript_summary}
                />
              </>
            )}
          </CardContent>
        </Card>
      )}

      {/* Concept context */}
      {concept && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Concept: {concept.display_name || concept.name}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {concept.description && (
              <p className="text-sm">{concept.description}</p>
            )}
            <div className="flex gap-4">
              {concept.schwartz_sophistication && (
                <Badge variant="outline">
                  {concept.schwartz_sophistication}
                </Badge>
              )}
              {subGroupName && (
                <Badge variant="secondary">Sub-group: {subGroupName}</Badge>
              )}
            </div>
            {concept.belief_mapping && (
              <div className="text-xs text-muted-foreground">
                <strong>Belief mapping:</strong> {concept.belief_mapping}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Copy Variations */}
      {copyVariations && copyVariations.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Copy Variations</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {copyVariations.map((v, i) => (
                <div key={v.id} className="space-y-1">
                  <div className="text-xs font-medium text-muted-foreground">
                    Variation {v.variation_number}
                  </div>
                  {v.primary_text && (
                    <p className="text-sm">{v.primary_text}</p>
                  )}
                  <div className="flex gap-4 text-xs">
                    {v.headline && (
                      <span>
                        <strong>Headline:</strong> {v.headline}
                      </span>
                    )}
                    {v.description && (
                      <span>
                        <strong>Desc:</strong> {v.description}
                      </span>
                    )}
                  </div>
                  {i < copyVariations.length - 1 && <Separator className="mt-3" />}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function MetadataField({
  label,
  value,
  badge,
}: {
  label: string;
  value: string | null;
  badge?: boolean;
}) {
  if (!value) return null;
  return (
    <div>
      <h4 className="text-xs font-medium text-muted-foreground mb-1">
        {label}
      </h4>
      {badge ? (
        <Badge variant="outline" className="text-xs">
          {value}
        </Badge>
      ) : (
        <p className="text-sm">{value}</p>
      )}
    </div>
  );
}
