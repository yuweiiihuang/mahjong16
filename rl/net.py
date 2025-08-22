
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
except Exception as e:
    torch = None
    nn = object
    F = None

class PolicyValueNet(nn.Module if torch else object):
    def __init__(self, obs_dim: int, act_dim: int):
        if torch is None:
            raise RuntimeError("未安裝 PyTorch，請先安裝後再使用 rl/net.py")
        super().__init__()
        self.fc1 = nn.Linear(obs_dim, 512)
        self.fc2 = nn.Linear(512, 512)
        self.pi = nn.Linear(512, act_dim)
        self.v  = nn.Linear(512, 1)

    def forward(self, x, legal_mask=None):
        h = F.relu(self.fc1(x)); h = F.relu(self.fc2(h))
        logits = self.pi(h)
        if legal_mask is not None:
            logits = logits + (legal_mask.clamp(min=1e-6)).log()
        value = self.v(h).tanh().squeeze(-1)
        return logits, value
