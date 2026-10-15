"""Candidate-scoring actor/critic and versioned local checkpoints (optional PyTorch)."""
from __future__ import annotations

from pathlib import Path
import random

import torch
from torch import nn

from app.hand_store import open_private_record
from rl.encoding import ENCODING_VERSION, encode


def batch(observations: list[dict], device: str = "cpu") -> tuple:
    """Pad only the candidate axis; padded actions have exactly zero probability."""
    encoded = [encode(obs) for obs in observations]
    states = torch.tensor([state for state, _ in encoded], device=device)
    count = max(len(actions) for _, actions in encoded)
    actions = torch.zeros(len(encoded), count, len(encoded[0][1][0]), device=device)
    mask = torch.zeros(len(encoded), count, dtype=torch.bool, device=device)
    for i, (_, candidates) in enumerate(encoded):
        actions[i, :len(candidates)] = torch.tensor(candidates, device=device)
        mask[i, :len(candidates)] = True
    return states, actions, mask


class PolicyValueNet(nn.Module):
    """Score each legal action conditioned on state; estimate undiscounted net payment."""

    def __init__(self, obs_dim: int, act_dim: int, hidden: int = 128) -> None:
        super().__init__()
        self.dimensions = (obs_dim, act_dim, hidden)
        self.state = nn.Sequential(nn.Linear(obs_dim, hidden), nn.ReLU())
        self.policy = nn.Sequential(nn.Linear(hidden + act_dim, hidden), nn.ReLU(),
                                    nn.Linear(hidden, 1))
        self.value = nn.Linear(hidden, 1)

    def forward(self, states: torch.Tensor, actions: torch.Tensor,
                mask: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Produce logits over candidates and an unbounded value for each observation."""
        hidden = self.state(states)
        joined = torch.cat((hidden[:, None].expand(-1, actions.shape[1], -1), actions), -1)
        logits = self.policy(joined).squeeze(-1).masked_fill(~mask, -torch.inf)
        return logits, self.value(hidden).squeeze(-1)

    @torch.no_grad()
    def choose(self, obs: dict) -> dict:
        """Choose deterministically from a safe player-view observation."""
        device = str(next(self.parameters()).device)
        logits, _ = self(*batch([obs], device))
        return obs["legal_actions"][int(logits[0].argmax())]


def save_checkpoint(path: Path, model: PolicyValueNet, spec: dict, *, stage: str,
                    optimizer: torch.optim.Optimizer, progress: dict) -> None:
    """Publish a complete owner-only checkpoint without overwriting another run."""
    payload = {"format_version": 1, "encoding_version": ENCODING_VERSION, "spec": spec,
               "dimensions": model.dimensions, "model": model.state_dict(), "stage": stage,
               "optimizer": optimizer.state_dict(), "progress": progress,
               "torch_rng": torch.get_rng_state(), "python_rng": random.getstate()}
    # The binary buffer shares the existing atomic private-output lifecycle.
    with open_private_record(path) as handle:
        torch.save(payload, handle.buffer)


def load_checkpoint(path: Path, spec: dict) -> tuple[PolicyValueNet, dict]:
    """Load tensors and primitives only, rejecting changed rules or observation contracts."""
    payload = torch.load(path, map_location="cpu", weights_only=True)
    if (payload.get("format_version") != 1
            or payload.get("encoding_version") != ENCODING_VERSION
            or payload.get("spec") != spec):
        raise ValueError("Checkpoint rules, engine or encoding do not match")
    model = PolicyValueNet(*payload["dimensions"])
    model.load_state_dict(payload["model"])
    model.eval()
    return model, payload
