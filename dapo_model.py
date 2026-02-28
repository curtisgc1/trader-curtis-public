"""
DAPO (Decoupled Advantage Policy Optimization) for stock trading.

Adapted from: "A New DAPO Algorithm for Stock Trading" (arXiv:2505.06408)

Key innovations over PPO:
  - Asymmetric clipping: separate epsilon_low / epsilon_high thresholds
  - Group-relative advantage normalization (within state groups)
  - Dynamic sampling: filter out states where all group advantages are zero
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.distributions import Normal


# ---------------------------------------------------------------------------
# Neural network building blocks
# ---------------------------------------------------------------------------

def _build_mlp(
    input_dim: int,
    hidden_sizes: Tuple[int, ...],
    activation: nn.Module = nn.Tanh(),
) -> nn.Sequential:
    """Build an MLP with tanh activations between layers."""
    layers: list[nn.Module] = []
    in_dim = input_dim
    for h in hidden_sizes:
        layers.append(nn.Linear(in_dim, h))
        layers.append(activation)
        in_dim = h
    return nn.Sequential(*layers)


class MLPActorCritic(nn.Module):
    """
    Actor-Critic network for continuous action spaces.

    Both actor and critic share an MLP backbone with tanh activations.
    Actor outputs mean and log_std; critic outputs a scalar value estimate.
    """

    LOG_STD_MIN: float = -20.0
    LOG_STD_MAX: float = 2.0

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_sizes: Tuple[int, ...] = (512, 512),
    ) -> None:
        super().__init__()
        self.state_dim = state_dim
        self.action_dim = action_dim

        # Shared backbone
        self.backbone = _build_mlp(state_dim, hidden_sizes)
        backbone_out = hidden_sizes[-1] if hidden_sizes else state_dim

        # Actor head: mean + log_std
        self.actor_mean = nn.Linear(backbone_out, action_dim)
        self.actor_log_std = nn.Linear(backbone_out, action_dim)

        # Critic head: scalar value
        self.critic_head = nn.Linear(backbone_out, 1)

        self._init_weights()

    def _init_weights(self) -> None:
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.orthogonal_(module.weight, gain=np.sqrt(2))
                nn.init.zeros_(module.bias)
        # Actor output layers use smaller gain for stability
        nn.init.orthogonal_(self.actor_mean.weight, gain=0.01)
        nn.init.orthogonal_(self.critic_head.weight, gain=1.0)

    def forward(
        self, state: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Returns (mean, log_std, value) given a batch of states.
        """
        features = self.backbone(state)
        mean = self.actor_mean(features)
        log_std = self.actor_log_std(features).clamp(self.LOG_STD_MIN, self.LOG_STD_MAX)
        value = self.critic_head(features).squeeze(-1)
        return mean, log_std, value

    def get_distribution(self, state: torch.Tensor) -> Normal:
        mean, log_std, _ = self.forward(state)
        return Normal(mean, log_std.exp())

    def evaluate_actions(
        self, state: torch.Tensor, action: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Returns (log_prob, entropy, value) for given state-action pairs.
        """
        mean, log_std, value = self.forward(state)
        dist = Normal(mean, log_std.exp())
        log_prob = dist.log_prob(action).sum(dim=-1)
        entropy = dist.entropy().sum(dim=-1)
        return log_prob, entropy, value


# ---------------------------------------------------------------------------
# Replay / rollout buffer with group-relative advantage computation
# ---------------------------------------------------------------------------

class DAPOBuffer:
    """
    Rollout buffer for DAPO.

    Stores trajectories and computes group-relative advantages using
    GAE-lambda followed by normalization within state groups.
    """

    def __init__(
        self,
        capacity: int,
        state_dim: int,
        action_dim: int,
        group_size: int = 8,
        gamma: float = 0.99,
        lam: float = 0.95,
        device: torch.device = torch.device("cpu"),
    ) -> None:
        self.capacity = capacity
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.group_size = group_size
        self.gamma = gamma
        self.lam = lam
        self.device = device
        self.ptr = 0
        self.size = 0

        self.states = np.zeros((capacity, state_dim), dtype=np.float32)
        self.actions = np.zeros((capacity, action_dim), dtype=np.float32)
        self.rewards = np.zeros(capacity, dtype=np.float32)
        self.values = np.zeros(capacity, dtype=np.float32)
        self.log_probs = np.zeros(capacity, dtype=np.float32)
        self.dones = np.zeros(capacity, dtype=np.float32)
        self.advantages = np.zeros(capacity, dtype=np.float32)
        self.returns = np.zeros(capacity, dtype=np.float32)

    def store(
        self,
        state: np.ndarray,
        action: np.ndarray,
        reward: float,
        value: float,
        log_prob: float,
        done: bool,
    ) -> None:
        idx = self.ptr % self.capacity
        self.states[idx] = state
        self.actions[idx] = action
        self.rewards[idx] = reward
        self.values[idx] = value
        self.log_probs[idx] = log_prob
        self.dones[idx] = float(done)
        self.ptr += 1
        self.size = min(self.size + 1, self.capacity)

    def compute_advantages(self, last_value: float = 0.0) -> None:
        """
        1. Compute GAE-lambda advantages over the stored trajectory.
        2. Group-relative normalization: normalize within groups of
           `group_size` consecutive transitions by dividing by the
           group standard deviation (+ eps for stability).
        """
        n = self.size
        gae = 0.0
        for t in reversed(range(n)):
            next_val = last_value if t == n - 1 else self.values[t + 1]
            next_non_terminal = 1.0 - self.dones[t]
            delta = self.rewards[t] + self.gamma * next_val * next_non_terminal - self.values[t]
            gae = delta + self.gamma * self.lam * next_non_terminal * gae
            self.advantages[t] = gae
            self.returns[t] = gae + self.values[t]

        # Group-relative normalization
        eps = 1e-8
        for start in range(0, n, self.group_size):
            end = min(start + self.group_size, n)
            group_adv = self.advantages[start:end]
            std = group_adv.std()
            self.advantages[start:end] = group_adv / (std + eps)

    def get(self) -> dict[str, torch.Tensor]:
        """Return all stored transitions as batched tensors."""
        n = self.size
        data = {
            "states": torch.as_tensor(self.states[:n], dtype=torch.float32, device=self.device),
            "actions": torch.as_tensor(self.actions[:n], dtype=torch.float32, device=self.device),
            "rewards": torch.as_tensor(self.rewards[:n], dtype=torch.float32, device=self.device),
            "values": torch.as_tensor(self.values[:n], dtype=torch.float32, device=self.device),
            "log_probs": torch.as_tensor(self.log_probs[:n], dtype=torch.float32, device=self.device),
            "dones": torch.as_tensor(self.dones[:n], dtype=torch.float32, device=self.device),
            "advantages": torch.as_tensor(self.advantages[:n], dtype=torch.float32, device=self.device),
            "returns": torch.as_tensor(self.returns[:n], dtype=torch.float32, device=self.device),
        }
        return data

    def reset(self) -> None:
        self.ptr = 0
        self.size = 0


# ---------------------------------------------------------------------------
# DAPO Agent
# ---------------------------------------------------------------------------

class DAPOAgent:
    """
    DAPO (Decoupled Advantage Policy Optimization) agent.

    Key differences from PPO:
      - Asymmetric clipping: epsilon_low for ratio < 1, epsilon_high for ratio > 1
      - Group-relative advantage normalization in the buffer
      - Dynamic sampling: states where all group advantages are 0 are filtered out
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_sizes: Tuple[int, ...] = (512, 512),
        lr: float = 3e-4,
        gamma: float = 0.99,
        lam: float = 0.95,
        epsilon_low: float = 0.2,
        epsilon_high: float = 0.28,
        group_size: int = 8,
        target_kl: float = 0.02,
        vf_coef: float = 0.5,
        ent_coef: float = 0.01,
        max_grad_norm: float = 0.5,
        device: Optional[str] = None,
    ) -> None:
        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        self.state_dim = state_dim
        self.action_dim = action_dim
        self.gamma = gamma
        self.lam = lam
        self.epsilon_low = epsilon_low
        self.epsilon_high = epsilon_high
        self.group_size = group_size
        self.target_kl = target_kl
        self.vf_coef = vf_coef
        self.ent_coef = ent_coef
        self.max_grad_norm = max_grad_norm

        self.ac = MLPActorCritic(
            state_dim=state_dim,
            action_dim=action_dim,
            hidden_sizes=hidden_sizes,
        ).to(self.device)

        self.optimizer = optim.Adam(self.ac.parameters(), lr=lr)

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    def select_action(
        self, state: np.ndarray
    ) -> Tuple[np.ndarray, float, float]:
        """
        Sample an action from the current policy.

        Returns:
            action    (np.ndarray): sampled action clipped to [-1, 1]
            log_prob  (float):      log probability of the action
            value     (float):      critic value estimate
        """
        state_t = torch.as_tensor(state, dtype=torch.float32, device=self.device).unsqueeze(0)
        with torch.no_grad():
            mean, log_std, value = self.ac(state_t)
            dist = Normal(mean, log_std.exp())
            action_t = dist.sample()
            log_prob_t = dist.log_prob(action_t).sum(dim=-1)

        action = action_t.squeeze(0).cpu().numpy()
        action = np.clip(action, -1.0, 1.0)
        log_prob = float(log_prob_t.item())
        value_scalar = float(value.item())
        return action, log_prob, value_scalar

    def predict(self, state: np.ndarray) -> np.ndarray:
        """
        Inference-only: returns the deterministic (mean) action as a numpy array.
        No gradient computation.
        """
        state_t = torch.as_tensor(state, dtype=torch.float32, device=self.device).unsqueeze(0)
        with torch.no_grad():
            mean, _, _ = self.ac(state_t)
        action = mean.squeeze(0).cpu().numpy()
        return np.clip(action, -1.0, 1.0)

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def _dapo_clip(
        self,
        ratio: torch.Tensor,
        advantages: torch.Tensor,
    ) -> torch.Tensor:
        """
        Asymmetric DAPO clip:
          - When advantage > 0 (ratio should increase): clip at 1 + epsilon_high
          - When advantage < 0 (ratio should decrease): clip at 1 - epsilon_low
        """
        clip_high = torch.clamp(ratio, max=1.0 + self.epsilon_high)
        clip_low = torch.clamp(ratio, min=1.0 - self.epsilon_low)
        clipped = torch.where(advantages >= 0, clip_high, clip_low)
        return torch.min(ratio * advantages, clipped * advantages)

    def _dynamic_sample_mask(
        self, advantages: torch.Tensor
    ) -> torch.Tensor:
        """
        Dynamic sampling: for each group, if all advantages in the group are
        (approximately) zero, mask out those transitions so they don't
        contribute to the policy gradient.

        Returns a boolean mask of shape (N,) — True means keep.
        """
        n = advantages.shape[0]
        mask = torch.ones(n, dtype=torch.bool, device=self.device)
        eps = 1e-8
        for start in range(0, n, self.group_size):
            end = min(start + self.group_size, n)
            group = advantages[start:end]
            if (group.abs() < eps).all():
                mask[start:end] = False
        return mask

    def update(self, buffer: DAPOBuffer, n_epochs: int = 10) -> dict[str, float]:
        """
        Run DAPO policy update on the data stored in `buffer`.

        Returns a dict of training metrics (losses, kl, clip fraction).
        """
        data = buffer.get()
        states = data["states"]
        actions = data["actions"]
        old_log_probs = data["log_probs"]
        advantages = data["advantages"]
        returns = data["returns"]

        # Dynamic sampling mask
        keep_mask = self._dynamic_sample_mask(advantages)
        if keep_mask.sum() == 0:
            # Nothing to train on
            return {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0, "kl": 0.0}

        states = states[keep_mask]
        actions = actions[keep_mask]
        old_log_probs = old_log_probs[keep_mask]
        advantages = advantages[keep_mask]
        returns = returns[keep_mask]

        metrics: dict[str, list[float]] = {
            "policy_loss": [],
            "value_loss": [],
            "entropy": [],
            "kl": [],
            "clip_fraction": [],
        }

        for _ in range(n_epochs):
            log_probs, entropy, values = self.ac.evaluate_actions(states, actions)
            ratio = torch.exp(log_probs - old_log_probs)

            # Approximate KL for early stopping
            with torch.no_grad():
                approx_kl = ((ratio - 1) - (log_probs - old_log_probs)).mean().item()

            if approx_kl > 1.5 * self.target_kl:
                break

            # DAPO asymmetric policy loss
            policy_loss = -self._dapo_clip(ratio, advantages).mean()

            # Value function loss (MSE)
            value_loss = ((values - returns) ** 2).mean()

            # Entropy bonus
            entropy_loss = -entropy.mean()

            loss = policy_loss + self.vf_coef * value_loss + self.ent_coef * entropy_loss

            self.optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(self.ac.parameters(), self.max_grad_norm)
            self.optimizer.step()

            # Clip fraction tracking
            with torch.no_grad():
                clipped = ((ratio < 1.0 - self.epsilon_low) | (ratio > 1.0 + self.epsilon_high)).float().mean().item()

            metrics["policy_loss"].append(policy_loss.item())
            metrics["value_loss"].append(value_loss.item())
            metrics["entropy"].append(-entropy_loss.item())
            metrics["kl"].append(approx_kl)
            metrics["clip_fraction"].append(clipped)

        return {k: float(np.mean(v)) if v else 0.0 for k, v in metrics.items()}

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        """Save model and optimizer state to a checkpoint file."""
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        torch.save(
            {
                "model_state_dict": self.ac.state_dict(),
                "optimizer_state_dict": self.optimizer.state_dict(),
                "config": {
                    "state_dim": self.state_dim,
                    "action_dim": self.action_dim,
                    "gamma": self.gamma,
                    "lam": self.lam,
                    "epsilon_low": self.epsilon_low,
                    "epsilon_high": self.epsilon_high,
                    "group_size": self.group_size,
                    "target_kl": self.target_kl,
                    "vf_coef": self.vf_coef,
                    "ent_coef": self.ent_coef,
                },
            },
            path,
        )

    def load(self, path: str) -> None:
        """Load model and optimizer state from a checkpoint file."""
        checkpoint = torch.load(path, map_location=self.device)
        self.ac.load_state_dict(checkpoint["model_state_dict"])
        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])


# ---------------------------------------------------------------------------
# Smoke test (only runs when executed directly)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import tempfile

    STATE_DIM = 64
    ACTION_DIM = 4
    BUFFER_SIZE = 256
    GROUP_SIZE = 8

    print("=== DAPO smoke test ===")

    agent = DAPOAgent(
        state_dim=STATE_DIM,
        action_dim=ACTION_DIM,
        hidden_sizes=(512, 512),
        lr=3e-4,
        gamma=0.99,
        lam=0.95,
        epsilon_low=0.2,
        epsilon_high=0.28,
        group_size=GROUP_SIZE,
        target_kl=0.02,
    )
    print(f"Device: {agent.device}")

    buf = DAPOBuffer(
        capacity=BUFFER_SIZE,
        state_dim=STATE_DIM,
        action_dim=ACTION_DIM,
        group_size=GROUP_SIZE,
        gamma=0.99,
        lam=0.95,
        device=agent.device,
    )

    rng = np.random.default_rng(42)
    for _ in range(BUFFER_SIZE):
        s = rng.standard_normal(STATE_DIM).astype(np.float32)
        a, lp, v = agent.select_action(s)
        r = float(rng.standard_normal())
        d = bool(rng.random() < 0.05)
        buf.store(s, a, r, v, lp, d)

    buf.compute_advantages(last_value=0.0)
    metrics = agent.update(buf, n_epochs=4)
    print(f"Update metrics: {metrics}")

    s_test = rng.standard_normal(STATE_DIM).astype(np.float32)
    action = agent.predict(s_test)
    print(f"Predict output shape: {action.shape}, range: [{action.min():.3f}, {action.max():.3f}]")

    with tempfile.TemporaryDirectory() as tmpdir:
        ckpt_path = os.path.join(tmpdir, "dapo_test.pt")
        agent.save(ckpt_path)
        agent.load(ckpt_path)
        print(f"Save/load OK: {ckpt_path}")

    print("=== All checks passed ===")
