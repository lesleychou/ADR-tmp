import numpy as np
import torch
import torch.nn as nn
from network import ActorNetwork, CriticNetwork
from torch.distributions import Categorical

RAND_RANGE = 1000


def entropy_weight_decay_func(epoch):
    # linear decay
    return np.maximum((1-0.1)/(10**5) * epoch + 1, 0.1)


class A3C(object):
    def __init__(self, is_central, model_type, s_dim, action_dim,
                 actor_lr=1e-4, critic_lr=1e-3):
        self.s_dim = s_dim
        self.a_dim = action_dim
        self.discount = 0.99
        self.entropy_weight = 0.5
        self.entropy_eps = 1e-6
        self.model_type = model_type

        self.is_central = is_central
        # self.device=torch.device("cuda:0" if torch.cuda.is_available() else
        # "cpu")
        self.device = torch.device(
            "cpu" if torch.cuda.is_available() else "cpu")

        self.actor_network = ActorNetwork(
            self.s_dim, self.a_dim).to(self.device)
        if self.is_central:
            # unify default parameters for tensorflow and pytorch
            self.actor_optim = torch.optim.RMSprop(
                self.actor_network.parameters(), lr=actor_lr, alpha=0.9,
                eps=1e-10)
            self.actor_optim.zero_grad()
            if model_type < 2:
                '''
                model==0 mean original
                model==1 mean critic_td
                model==2 mean only actor
                '''
                self.criticNetwork = CriticNetwork(
                    self.s_dim, self.a_dim).to(self.device)
                self.criticOptim = torch.optim.RMSprop(
                    self.criticNetwork.parameters(), lr=critic_lr, alpha=0.9,
                    eps=1e-10)
                self.criticOptim.zero_grad()
        else:
            self.actor_network.eval()

        self.loss_function = nn.MSELoss()

    def getNetworkGradient(self, s_batch, a_batch, r_batch, terminal, epoch):
        s_batch = torch.cat(s_batch).to(self.device)
        a_batch = torch.LongTensor(a_batch).to(self.device)
        r_batch = torch.tensor(r_batch).to(self.device)
        R_batch = torch.zeros(r_batch.shape).to(self.device)

        R_batch[-1] = r_batch[-1]
        for t in reversed(range(r_batch.shape[0]-1)):
            R_batch[t] = r_batch[t] + self.discount*R_batch[t+1]

        if self.model_type < 2:
            with torch.no_grad():
                v_batch = self.criticNetwork.forward(
                    s_batch).squeeze().to(self.device)
            td_batch = R_batch-v_batch
        else:
            td_batch = R_batch

        probability = self.actor_network.forward(s_batch)
        m_probs = Categorical(probability)
        log_probs = m_probs.log_prob(a_batch)
        actor_loss = torch.sum(log_probs*(-td_batch))
        # entropy_loss=-self.entropy_weight*torch.sum(m_probs.entropy())
        entropy_loss = - \
            entropy_weight_decay_func(epoch)*torch.sum(m_probs.entropy())
        actor_loss = actor_loss+entropy_loss
        actor_loss.backward()

        if self.model_type < 2:
            if self.model_type == 0:
                # original
                critic_loss = self.loss_function(
                    R_batch, self.criticNetwork.forward(s_batch).squeeze())
            else:
                # cricit_td
                v_batch = self.criticNetwork.forward(s_batch[:-1]).squeeze()
                next_v_batch = self.criticNetwork.forward(
                    s_batch[1:]).squeeze().detach()
                critic_loss = self.loss_function(
                    r_batch[:-1]+self.discount*next_v_batch, v_batch)

            critic_loss.backward()

        # use the feature of accumulating gradient in pytorch

    def actionSelect(self, stateInputs):
        if not self.is_central:
            with torch.no_grad():
                stateInputs_gpu = stateInputs.to(self.device)
                probability = self.actor_network.forward(stateInputs_gpu)
                m = Categorical(probability)
                action = m.sample().item()
                return action, probability.cpu().tolist()[0]

    def hardUpdateActorNetwork(self, actor_net_params):
        for target_param, source_param in zip(self.actor_network.parameters(),
                                              actor_net_params):
            target_param.data.copy_(source_param.data)

    def updateNetwork(self):
        # use the feature of accumulating gradient in pytorch
        if self.is_central:
            self.actor_optim.step()
            self.actor_optim.zero_grad()
            if self.model_type < 2:
                self.criticOptim.step()
                self.criticOptim.zero_grad()

    def getActorParam(self):
        return list(self.actor_network.parameters())

    def getCriticParam(self):
        return list(self.criticNetwork.parameters())


def compute_entropy(x):
    """Given vector x, computes the entropy H(x) = - sum( p * log(p))."""
    H = 0.0
    for i in range(len(x)):
        if 0 < x[i] < 1:
            H -= x[i] * np.log(x[i])
    return H


# if __name__ == '__main__':
#     # test maddpg in convid,ok
#     SINGLE_S_LEN = 19
#
#     AGENT_NUM = 1
#     BATCH_SIZE = 200
#
#     S_INFO = 6
#     S_LEN = 8
#     ACTION_DIM = 6
#
#     discount = 0.9
#
#     obj = A3C(False, 0, [S_INFO, S_LEN], ACTION_DIM)
#
#     episode = 3000
#     for i in range(episode):
#
#         state = torch.randn(AGENT_NUM, S_INFO, S_LEN)
#         action = torch.randint(0, 5, (AGENT_NUM,), dtype=torch.long)
#         reward = torch.randn(AGENT_NUM)
#         probability, _ = obj.actionSelect(state)
#         print(probability)
#
