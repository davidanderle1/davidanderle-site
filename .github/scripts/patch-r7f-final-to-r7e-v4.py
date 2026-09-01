#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

PATH = Path('.github/workflows/r7f-portable-final-verification.yml')
START_MARKER = '      - name: Select only a green generator-bound portable R7E\n'
END_MARKER = '      - name: Adapt proven verifier only at explicit portable boundaries\n'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one anchor, found {count}')
    return text.replace(old, new, 1)


def main() -> None:
    text = PATH.read_text(encoding='utf-8')
    text = replace_once(
        text,
        '  R7E_BRANCH: r7e-portable-json-schema-verification-20260831\n'
        '  R7E_WORKFLOW_PATH: .github/workflows/r7e-portable-json-schema-verification.yml\n',
        '  R7E_BRANCH: r7e-portable-self-recording-final-20260901\n'
        '  R7E_WORKFLOW_PATH: .github/workflows/r7e-portable-authoritative-executor-v4.yml\n'
        "  R7E_RUN_ID: '33509839046'\n"
        '  R7E_COMMIT: ea592cde4f4a09f18442308ff14e1eeb2621bf33\n'
        "  R7E_EVIDENCE_ARTIFACT_ID: '9801298633'\n"
        '  R7E_EVIDENCE_ARTIFACT_NAME: r7e-portable-self-recording-v4-evidence-ea592cde4f4a09f18442308ff14e1eeb2621bf33\n'
        '  R7E_EVIDENCE_ARTIFACT_DIGEST: sha256:8c98377f442bdc1ab5ed45f240c38ec6773ca29ca8f887375e0ec7dc6aa99d3a\n'
        "  R7E_LINEAGE_ARTIFACT_ID: '9801300076'\n"
        '  R7E_LINEAGE_ARTIFACT_NAME: r7e-portable-self-recording-v4-lineage-ea592cde4f4a09f18442308ff14e1eeb2621bf33\n'
        '  R7E_LINEAGE_ARTIFACT_DIGEST: sha256:0c5190fa0e0c42b2a5f80ec6fe8211743e0680d3de4dece8d5df98eb10e8cc33\n',
        'selector environment',
    )

    start = text.index(START_MARKER)
    end = text.index(END_MARKER, start)
    step = text[start:end]

    step = replace_once(
        step,
        '              [[ -n "$run_id" && -n "$head_sha" ]] || continue\n',
        '              [[ -n "$run_id" && -n "$head_sha" ]] || continue\n'
        '              [[ "$run_id" == "$R7E_RUN_ID" && "$head_sha" == "$R7E_COMMIT" ]] || continue\n',
        'exact run pin',
    )
    step = replace_once(
        step,
        '              jq --arg prefix "r7e-portable-json-schema-evidence-$head_sha" \\\n',
        '              jq --arg prefix "$R7E_EVIDENCE_ARTIFACT_NAME" \\\n',
        'evidence artifact name',
    )
    step = replace_once(
        step,
        '              artifact_digest="$(jq -r \'.digest\' /tmp/r7e-artifact.json)"\n',
        '              artifact_digest="$(jq -r \'.digest\' /tmp/r7e-artifact.json)"\n'
        '              [[ "$artifact_id" == "$R7E_EVIDENCE_ARTIFACT_ID" ]] || continue\n'
        '              [[ "$artifact_name" == "$R7E_EVIDENCE_ARTIFACT_NAME" ]] || continue\n'
        '              [[ "$artifact_digest" == "$R7E_EVIDENCE_ARTIFACT_DIGEST" ]] || continue\n',
        'evidence artifact tuple',
    )

    manifest_anchor = '''              [[ -f /tmp/r7e-artifact/R7E_ARTIFACT_SHA256SUMS.txt ]] || continue
              if ! (cd /tmp/r7e-artifact && sha256sum --check --strict R7E_ARTIFACT_SHA256SUMS.txt >/tmp/r7e-internal-manifest.txt); then
                continue
              fi
'''
    lineage = '''
              jq --arg name "$R7E_LINEAGE_ARTIFACT_NAME" \\
                '[.artifacts[] | select(.name==$name and .expired==false)]' \\
                /tmp/r7e-artifacts.json > /tmp/r7e-lineage-matches.json
              [[ "$(jq 'length' /tmp/r7e-lineage-matches.json)" -eq 1 ]] || continue
              jq '.[0]' /tmp/r7e-lineage-matches.json > /tmp/r7e-lineage-artifact.json
              lineage_id="$(jq -r '.id' /tmp/r7e-lineage-artifact.json)"
              lineage_name="$(jq -r '.name' /tmp/r7e-lineage-artifact.json)"
              lineage_digest="$(jq -r '.digest' /tmp/r7e-lineage-artifact.json)"
              [[ "$lineage_id" == "$R7E_LINEAGE_ARTIFACT_ID" ]] || continue
              [[ "$lineage_name" == "$R7E_LINEAGE_ARTIFACT_NAME" ]] || continue
              [[ "$lineage_digest" == "$R7E_LINEAGE_ARTIFACT_DIGEST" ]] || continue

              rm -rf /tmp/r7e-lineage /tmp/r7e-lineage.zip
              mkdir -p /tmp/r7e-lineage
              if ! curl --fail --silent --show-error --location \\
                    -H "Authorization: Bearer $GH_TOKEN" \\
                    -H 'Accept: application/vnd.github+json' \\
                    "https://api.github.com/repos/$repo/actions/artifacts/$lineage_id/zip" \\
                    --output /tmp/r7e-lineage.zip; then
                continue
              fi
              [[ "sha256:$(sha256sum /tmp/r7e-lineage.zip | awk '{print $1}')" == "$lineage_digest" ]] || continue
              if ! python3 - <<'PY_LINEAGE_ZIP'
          import stat, zipfile
          from pathlib import PurePosixPath
          with zipfile.ZipFile('/tmp/r7e-lineage.zip') as z:
              names=[]
              for info in z.infolist():
                  q=PurePosixPath(info.filename)
                  if q.is_absolute() or '..' in q.parts or '\\\\' in info.filename:
                      raise SystemExit(1)
                  if ((info.external_attr >> 16) & 0o170000) == stat.S_IFLNK:
                      raise SystemExit(1)
                  names.append(info.filename)
              if len(names) != len(set(names)):
                  raise SystemExit(1)
              z.extractall('/tmp/r7e-lineage')
          PY_LINEAGE_ZIP
              then
                continue
              fi
              [[ -f /tmp/r7e-lineage/EXECUTOR_LINEAGE_SHA256SUMS.txt ]] || continue
              if ! (cd /tmp/r7e-lineage && sha256sum --check --strict EXECUTOR_LINEAGE_SHA256SUMS.txt >/tmp/r7e-lineage-manifest.txt); then
                continue
              fi
              if ! jq -e \\
                    --arg commit "$R7E_COMMIT" \\
                    --arg run "$R7E_RUN_ID" \\
                    --arg evidenceId "$R7E_EVIDENCE_ARTIFACT_ID" \\
                    --arg evidenceName "$R7E_EVIDENCE_ARTIFACT_NAME" \\
                    --arg evidenceDigest "$R7E_EVIDENCE_ARTIFACT_DIGEST" \\
                    '.schema=="R7E_PORTABLE_SELF_RECORDING_AUTHORITATIVE_TUPLE_V4" and
                     .passed==true and .branchHeadUnchanged==true and
                     .commit==$commit and (.runId|tostring)==$run and
                     (.artifact.id|tostring)==$evidenceId and
                     .artifact.name==$evidenceName and .artifact.digest==$evidenceDigest and
                     .workflowPath==".github/workflows/r7e-portable-authoritative-executor-v4.yml" and
                     .sourceFileCount==146 and .generatedPlan.executedRunStepCount==18 and
                     .candidateIdentity.axeIncompleteNodeCount==498 and
                     .candidateIdentity.portableSchemaContractVersion=="1.0.0"' \\
                    /tmp/r7e-lineage/portable-r7e-v4.json >/dev/null; then
                continue
              fi
'''
    step = replace_once(step, manifest_anchor, manifest_anchor + lineage, 'lineage authentication')

    copy_anchor = '              cp /tmp/r7e-artifact/R7E_EVIDENCE/R7E_CANDIDATE_IDENTITY.json builder-selection/r7e-identity.json\n'
    step = replace_once(
        step,
        copy_anchor,
        copy_anchor
        + '              cp /tmp/r7e-lineage-artifact.json builder-selection/r7e-lineage-artifact.json\n'
        + '              cp /tmp/r7e-lineage/portable-r7e-v4.json builder-selection/r7e-authoritative-tuple-v4.json\n'
        + '              cp /tmp/r7e-lineage/EXECUTOR_LINEAGE_SHA256SUMS.txt builder-selection/r7e-lineage-sha256sums.txt\n'
        + '              cp /tmp/r7e-lineage-manifest.txt builder-selection/r7e-lineage-manifest-check.txt\n',
        'lineage evidence copy',
    )

    text = text[:start] + step + text[end:]
    forbidden = (
        'R7E_BRANCH: r7e-portable-json-schema-verification-20260831',
        'r7e-portable-json-schema-evidence-$head_sha',
    )
    remaining = [item for item in forbidden if item in text]
    if remaining:
        raise SystemExit(f'stale selector tokens remain: {remaining}')
    required = (
        'R7E_PORTABLE_SELF_RECORDING_AUTHORITATIVE_TUPLE_V4',
        'R7E_LINEAGE_ARTIFACT_DIGEST',
        'r7e-authoritative-tuple-v4.json',
    )
    missing = [item for item in required if item not in text]
    if missing:
        raise SystemExit(f'pinned selector missing required tokens: {missing}')
    PATH.write_text(text, encoding='utf-8')
    print(f'patched {PATH} bytes={PATH.stat().st_size}')


if __name__ == '__main__':
    main()
