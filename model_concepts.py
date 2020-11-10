import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable
import numpy as np
import math

def to_contiguous(tensor):
    if tensor.is_contiguous():
        return tensor
    else:
        return tensor.contiguous()


class RewardCriterion(nn.Module):
    def __init__(self):
        super(RewardCriterion, self).__init__()

    def forward(self, seq, logprobs, reward):
        logprobs = to_contiguous(logprobs).view(-1)
        reward = to_contiguous(reward).view(-1)
        mask = (seq > 0).float()
        # add one to the right to count for the <eos> token
        mask = to_contiguous(torch.cat(
            [mask.new(mask.size(0), 1).fill_(1), mask[:, :-1]], 1)).view(-1)
        output = - logprobs * reward * Variable(mask)
        output = torch.sum(output) / torch.sum(mask)

        return output


class CrossEntropyCriterion(nn.Module):
    def __init__(self):
        super(CrossEntropyCriterion, self).__init__()

    def forward(self, pred, target, mask, bcmrscores=None):
        # truncate to the same size

        target = target[:, :pred.size(1)]
        mask = mask[:, :pred.size(1)]
        seq_len = pred.size(1)
        pred = to_contiguous(pred).view(-1, pred.size(2))
        target = to_contiguous(target).view(-1, 1)
        mask = to_contiguous(mask).view(-1, 1)

        output = -pred.gather(1, target) * mask
        if bcmrscores is not None:
            weights = bcmrscores.view(-1).unsqueeze(1).repeat(1, seq_len).view(-1, 1)
        else:
            weights = torch.ones(output.shape).cuda() 
        output = torch.sum(output*weights) / torch.sum(mask)

        return output


class FeatPool(nn.Module):
    def __init__(self, feat_dims, out_size, dropout, SQUEEZE=True):
        super(FeatPool, self).__init__()
        self.squeeze = SQUEEZE
        module_list = []
        for dim in feat_dims:
            module = nn.Sequential(
                nn.Linear(dim, out_size),
                nn.ReLU(),
                nn.Dropout(dropout))
            module_list += [module]
        self.feat_list = nn.ModuleList(module_list)


    def forward(self, feats):
        """
        feats is a list, each element is a tensor that have size (N x C x F)
        at the moment assuming that C == 1
        """
        if self.squeeze:
            out = torch.cat([m(feats[i].squeeze(1)) for i, m in enumerate(self.feat_list)], 1)
        else:
            out = torch.cat([m(feats[i]) for i, m in enumerate(self.feat_list)], 2)
        return out


class FeatExpander(nn.Module):

    def __init__(self, n=1):
        super(FeatExpander, self).__init__()
        self.n = n

    def forward(self, x):
        if self.n == 1:
            out = x
        else:
            if len(x.shape) == 2:
                out = Variable(x.data.new(self.n * x.size(0), x.size(1)), volatile=x.volatile)
                for i in range(x.size(0)):
                    out[i * self.n:(i + 1) * self.n] = x[i].expand(self.n, x.size(1))
            elif len(x.shape) == 3:
                out = Variable(x.data.new(self.n * x.size(0), x.size(1), x.size(2)), volatile=x.volatile)
                for i in range(x.size(0)):
                    out[i * self.n:(i + 1) * self.n] = x[i].expand(self.n, x.size(1), x.size(2))

        return out

    def set_n(self, x):
        self.n = x


class RNNUnit(nn.Module):

    def __init__(self, opt):
        super(RNNUnit, self).__init__()
        self.rnn_type = opt.rnn_type
        self.rnn_size = opt.rnn_size
        self.num_layers = opt.num_layers
        self.drop_prob_lm = opt.drop_prob_lm

        if opt.model_type == 'standard':
            self.input_size = opt.input_encoding_size
        elif opt.model_type in ['concat', 'manet']:
            self.input_size = opt.input_encoding_size + opt.video_encoding_size

        self.rnn = getattr(nn, self.rnn_type.upper())(self.input_size, self.rnn_size, self.num_layers, bias=False, dropout=self.drop_prob_lm)

    def forward(self, xt, state):
        output, state = self.rnn(xt.unsqueeze(0), state)
        return output.squeeze(0), state


class MANet(nn.Module):
    """
    MANet: Modal Attention
    """

    def __init__(self, video_encoding_size, rnn_size, num_feats):
        super(MANet, self).__init__()
        self.video_encoding_size = video_encoding_size
        self.rnn_size = rnn_size
        self.num_feats = num_feats

        self.f_feat_m = nn.Linear(self.video_encoding_size, self.num_feats)
        self.f_h_m = nn.Linear(self.rnn_size, self.num_feats)
        self.align_m = nn.Linear(self.num_feats, self.num_feats)

    def forward(self, x, h):
        f_feat = self.f_feat_m(x)
        f_h = self.f_h_m(h.squeeze(0))  # assuming now num_layers is 1
        att_weight = nn.Softmax()(self.align_m(nn.Tanh()(f_feat + f_h)))
        att_weight = att_weight.unsqueeze(2).expand(
            x.size(0), self.num_feats, int(self.video_encoding_size / self.num_feats))
        att_weight = att_weight.contiguous().view(x.size(0), x.size(1))
        return x * att_weight




class PositionalEncoding(nn.Module):

    def __init__(self, d_model, dropout=0.1, max_len=5000):
        super(PositionalEncoding, self).__init__()
        self.dropout = nn.Dropout(p=dropout)

        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0).transpose(0, 1)
        self.register_buffer('pe', pe)

    def forward(self, x):
        x = x + self.pe[:x.size(0), :]
        return self.dropout(x)

# TODO make a box enc to FIRST cat then encode, rather than encode then cat
# class BoxEnc(nn.Module):
#     def __init__(self, feat_dims, out_size, dropout, SQUEEZE=True):
#         super(BoxEnc, self).__init__()
#         self.squeeze = SQUEEZE
#         module_list = []
#         for dim in feat_dims:
#             module = nn.Sequential(
#                 nn.Linear(dim, out_size),
#                 nn.ReLU(),
#                 nn.Dropout(dropout))
#             module_list += [module]
#         self.feat_list = nn.ModuleList(module_list)
#
#
#     def forward(self, feats):
#         """
#         feats is a list, each element is a tensor that have size (N x C x F)
#         at the moment assuming that C == 1
#         """
#         if self.squeeze:
#             out = torch.cat([m(feats[i].squeeze(1)) for i, m in enumerate(self.feat_list)], 1)
#         else:
#             out = torch.cat([m(feats[i]) for i, m in enumerate(self.feat_list)], 2)
#         return out

class CaptionModelSVO(nn.Module):
    """
    Allow S V and O to be put into LTSM when --pass_all_svo is set to 1
    """

    def __init__(self, opt):
        super(CaptionModelSVO, self).__init__()
        self.vocab_size = opt.vocab_size
        self.input_encoding_size = opt.input_encoding_size
        self.rnn_type = opt.rnn_type
        self.rnn_size = opt.rnn_size
        self.att_size = opt.att_size
        self.num_layers = opt.num_layers
        self.drop_prob_lm = opt.drop_prob_lm
        self.seq_length = opt.seq_length
        self.bfeat_dims = opt.bfeat_dims
        self.feat_dims = opt.feat_dims
        self.num_feats = len(self.feat_dims)
        self.seq_per_img = opt.train_seq_per_img
        self.model_type = opt.model_type
        self.pass_all_svo = opt.pass_all_svo
        self.bos_index = 1  # index of the <bos> token
        self.ss_prob = 0
        self.mixer_from = 0
        self.attention_record = list()

        self.embed = nn.Embedding(self.vocab_size, self.input_encoding_size)  # word embedding layer (1-hot -> enc)
        self.logit = nn.Linear(self.rnn_size, self.vocab_size)  # logit embedding layer (enc -> vocab enc)
        self.dropout = nn.Dropout(self.drop_prob_lm)

        self.l2a_layer = nn.Linear(self.input_encoding_size, self.att_size)
        self.h2a_layer = nn.Linear(self.rnn_size, self.att_size)
        self.att_layer = nn.Linear(self.att_size, 1)

        self.init_weights()
        if self.model_type == 'standard':
            self.feat_pool = FeatPool(self.feat_dims[0:1], self.num_layers * self.rnn_size, self.drop_prob_lm)
        else:
            self.feat_pool = FeatPool(self.feat_dims, self.num_layers * self.rnn_size, self.drop_prob_lm)

            # encode the box features 1024 -> 512 and 4 -> 512 (linear>relu>dropout)
            self.bfeat_pool_q = FeatPool(self.bfeat_dims, self.num_layers * self.rnn_size, self.drop_prob_lm,
                                         SQUEEZE=False)
            self.bfeat_pool_k = FeatPool(self.bfeat_dims, self.num_layers * self.rnn_size, self.drop_prob_lm,
                                         SQUEEZE=False)
            self.bfeat_pool_v = FeatPool(self.bfeat_dims, self.num_layers * self.rnn_size, self.drop_prob_lm,
                                         SQUEEZE=False)

            # encode the visual features (linear>relu>dropout)
            # 2d cnn -> subject 1536>1024 and 4096>1024
            self.feat_pool_ds = FeatPool(self.feat_dims[0:1], self.num_layers * 2 * self.rnn_size, self.drop_prob_lm,
                                         SQUEEZE=False)
            # 2d cnn and verb enc feat -> object .. 1536>512 and 512>512
            self.feat_pool_do = FeatPool([self.feat_dims[0], self.input_encoding_size], self.num_layers * self.rnn_size,
                                         self.drop_prob_lm, SQUEEZE=False)
            # 3d cnn and subject enc feat -> verb .. 4096>512 and 512>512
            self.feat_pool_dv = FeatPool([self.feat_dims[1], self.input_encoding_size], self.num_layers * self.rnn_size,
                                         self.drop_prob_lm, SQUEEZE=False)

            self.feat_pool_f2h = FeatPool([2 * self.rnn_size], self.num_layers * self.rnn_size, self.drop_prob_lm,
                                          SQUEEZE=False)

        self.feat_expander = FeatExpander(self.seq_per_img)

        self.video_encoding_size = self.num_feats * self.num_layers * self.rnn_size
        opt.video_encoding_size = self.video_encoding_size
        self.core = RNNUnit(opt)  # the caption generation rnn LSTM(512) with input size 2048

        if self.model_type == 'manet':
            self.manet = MANet(self.video_encoding_size, self.rnn_size, self.num_feats)

    def set_ss_prob(self, p):
        self.ss_prob = p

    def set_mixer_from(self, t):
        """Set values of mixer_from
        if mixer_from > 0 then start MIXER training
        i.e:
        from t = 0 -> t = mixer_from -1: use XE training
        from t = mixer_from -> end: use RL training
        """
        self.mixer_from = t

    def set_seq_per_img(self, x):
        self.seq_per_img = x
        self.feat_expander.set_n(x)

    def init_weights(self):
        initrange = 0.1
        self.embed.weight.data.uniform_(-initrange, initrange)
        self.logit.bias.data.fill_(0)
        self.logit.weight.data.uniform_(-initrange, initrange)

    def init_hidden(self, batch_size):
        weight = next(self.parameters()).data

        if self.rnn_type == 'lstm':
            return (Variable(weight.new(self.num_layers, batch_size, self.rnn_size).zero_()),
                    Variable(weight.new(self.num_layers, batch_size, self.rnn_size).zero_()))
        else:
            return Variable(weight.new(self.num_layers, batch_size, self.rnn_size).zero_())

    def _svo_step(self, feats, bfeats, pos=None, expand_feat=1):
        # pos is svo gt vocab indexs

        # encode the box features with linear->relu->dropout layer into query, key, value feats
        q_feats = self.bfeat_pool_q(bfeats)
        k_feats = self.bfeat_pool_k(bfeats)
        v_feats = self.bfeat_pool_v(bfeats)

        # use the query and key encodings to calculate self-attention weights
        b_att = torch.matmul(q_feats, k_feats.transpose(1, 2)) / math.sqrt(q_feats.shape[-1])
        b_att = F.softmax(b_att, dim=-1)

        # record the attention weights, used for visualisation purposes
        att_rec = b_att.data.cpu().numpy()
        self.attention_record = [np.mean(att_rec[i], axis=0) for i in range(len(att_rec))]

        # apply the box attention to the value encodings
        b_rep = torch.matmul(b_att, v_feats)

        # generalized bb representation (add a random extra box)
        gb_rep = torch.cat((b_rep, torch.rand(b_rep.shape[0], 1, b_rep.shape[-1]).cuda()), 1)

        ################### SUBJECT ###################
        # encode the subject features
        dec_feat_s = self.feat_pool_ds(feats[0:1])

        # use the 2D CNN and box encodings to generate attention for the global box reps
        s_att = torch.matmul(dec_feat_s, gb_rep.transpose(1, 2)) / math.sqrt(dec_feat_s.shape[-1])
        s_att = F.softmax(s_att, -1)
        s_rep = torch.matmul(s_att, gb_rep)  # apply the att
        if expand_feat:  # expand to seq_per_img length
            s_rep = self.feat_expander(s_rep.squeeze(1)).unsqueeze(1)  # [seq_im * batch, 1, d]

        # encode the subject rep with a hidden layer
        s_hid = self.feat_pool_f2h([s_rep])
        # encode to logits and apply softmax to get word probabilities
        s_out = F.log_softmax(self.logit(s_hid), dim=-1)
        # argmax the subject
        s_it = F.softmax(self.logit(s_hid), dim=-1).argmax(-1)

        ################### VERB ###################
        if expand_feat:
            feat_v_exp = self.feat_expander(feats[1].squeeze(1)).unsqueeze(1)  # [seq_im * batch, d]
        else:
            feat_v_exp = feats[1].clone()

        # encode the verb feature and the subject word embedding
        if self.training and pos is not None:
            dec_feat_v = self.feat_pool_dv([feat_v_exp, self.embed(pos[:, 0]).unsqueeze(1)])
        else:
            dec_feat_v = self.feat_pool_dv([feat_v_exp, self.embed(s_it.squeeze(1)).unsqueeze(1)])

        # encode the verb rep with a hidden layer
        v_hid = self.feat_pool_f2h([dec_feat_v])
        # encode to logits and apply softmax to get word probabilities
        v_out = F.log_softmax(self.logit(v_hid), dim=-1)
        # argmax the verb
        v_it = F.softmax(self.logit(v_hid), dim=-1).argmax(-1)

        ################### OBJECT ###################
        if expand_feat:
            feat_o_exp = self.feat_expander(feats[0].squeeze(1)).unsqueeze(1)
        else:
            feat_o_exp = feats[0].clone()

        # encode the object feature and the verb word embedding
        if self.training and pos is not None:
            dec_feat_o = self.feat_pool_do([feat_o_exp, self.embed(pos[:, 1]).unsqueeze(1)])
        else:
            dec_feat_o = self.feat_pool_do([feat_o_exp, self.embed(v_it.squeeze(1)).unsqueeze(1)])

        # calculate attention over the box features based on the word emb
        if expand_feat:
            o_att = torch.matmul(dec_feat_o, self.feat_expander(gb_rep).transpose(1, 2)) / math.sqrt(
                dec_feat_o.shape[-1])
        else:
            o_att = torch.matmul(dec_feat_o, gb_rep.transpose(1, 2)) / math.sqrt(dec_feat_o.shape[-1])

        o_att = F.softmax(o_att, -1)
        if expand_feat:
            o_rep = torch.matmul(o_att, self.feat_expander(gb_rep))
        else:
            o_rep = torch.matmul(o_att, gb_rep)

        # encode the object rep with a hidden layer
        o_hid = self.feat_pool_f2h([o_rep])
        # encode to logits and apply softmax to get word probabilities
        o_out = F.log_softmax(self.logit(o_hid), dim=-1)
        # argmax the object
        o_it = F.softmax(self.logit(o_hid), dim=-1).argmax(-1)

        return torch.cat((s_out, v_out, o_out), dim=1), torch.cat((s_it, v_it, o_it), dim=1)

    def forward(self, feats, bfeats, seq, pos):
        fc_feats = self.feat_pool(feats)
        fc_feats = self.feat_expander(fc_feats)

        # get the svo features and vocab indexs
        svo_out, svo_it = self._svo_step(feats, bfeats, pos)

        ########### RNN ###########
        batch_size = fc_feats.size(0)
        state = self.init_hidden(batch_size)
        outputs = []
        sample_seq = []
        sample_logprobs = []

        # -- if <image feature> is input at the first step, use index -1
        # -- the <eos> token is not used for training
        start_i = -1 if self.model_type == 'standard' else 0
        end_i = seq.size(1) - 1

        for token_idx in range(start_i, end_i):
            if token_idx == -1:  # initially set xt as global feats
                xt = fc_feats
            else:
                # token_idx = 0 corresponding to the <BOS> token
                # (already encoded in seq)

                if self.training and token_idx >= 1 and self.ss_prob > 0.0:
                    sample_prob = fc_feats.data.new(batch_size).uniform_(0, 1)
                    sample_mask = sample_prob < self.ss_prob
                    if sample_mask.sum() == 0:
                        it = seq[:, token_idx].clone()
                    else:
                        sample_ind = sample_mask.nonzero().view(-1)
                        it = seq[:, token_idx].data.clone()
                        # fetch prev distribution: shape Nx(M+1)
                        prob_prev = torch.exp(outputs[-1].data)
                        sample_ind_tokens = torch.multinomial(prob_prev, 1).view(-1).index_select(0, sample_ind)
                        it.index_copy_(0, sample_ind, sample_ind_tokens)
                        it = Variable(it, requires_grad=False)
                elif self.training and self.mixer_from > 0 and token_idx >= self.mixer_from:
                    prob_prev = torch.exp(outputs[-1].data)
                    it = torch.multinomial(prob_prev, 1).view(-1)
                    it = Variable(it, requires_grad=False)
                else:
                    it = seq[:, token_idx].clone()

                if token_idx >= 1:
                    # store the seq and its logprobs
                    sample_seq.append(it.data)
                    logprobs = outputs[-1].gather(1, it.unsqueeze(1))
                    sample_logprobs.append(logprobs.view(-1))

                # break if all the sequences end, which requires EOS token = 0
                if it.data.sum() == 0:
                    break

                # get word embedding for the verb, concat with last pred word (it, rep as vocab index)
                if self.training:
                    if self.pass_all_svo:
                        lan_cont = self.embed(torch.cat((pos, it.unsqueeze(1)), 1))  # include sub and obj
                    else:
                        lan_cont = self.embed(torch.cat((pos[:, 1:2], it.unsqueeze(1)), 1))  # (bs * seq_per_img, 2, 512)
                else:
                    if self.pass_all_svo:
                        lan_cont = self.embed(torch.cat((svo_it, it.unsqueeze(1)), 1))  # include sub and obj
                    else:
                        lan_cont = self.embed(torch.cat((svo_it[:, 1:2], it.unsqueeze(1)), 1))

                if self.pass_all_svo:
                    hid_cont = state[0].transpose(0, 1).expand(lan_cont.shape[0], 4, state[0].shape[2])  # (bs * seq_per_img, 4, 512)
                else:
                    hid_cont = state[0].transpose(0, 1).expand(lan_cont.shape[0], 2, state[0].shape[2])  # (bs * seq_per_img, 2, 512)
                # calculate attention on encodings of the verb embedding and the RNN hidden state
                alpha = self.att_layer(torch.tanh(self.l2a_layer(lan_cont) + self.h2a_layer(hid_cont)))  # (bs * seq_per_img, 2, 1)
                alpha = F.softmax(alpha, dim=1).transpose(1, 2)  # (bs * seq_per_img, 1, 2)
                # apply the attention to the verb word embedding and the hidden layer emb
                xt = torch.matmul(alpha, lan_cont).squeeze(1)

            # generate next word
            if self.model_type == 'standard':
                output, state = self.core(xt, state)
            else:
                if self.model_type == 'manet':
                    fc_feats = self.manet(fc_feats, state[0])
                output, state = self.core(torch.cat([xt, fc_feats], 1), state)

            # generate the word softmax
            if token_idx >= 0:
                output = F.log_softmax(self.logit(self.dropout(output)), dim=1)
                outputs.append(output)

        # only returns outputs of seq input
        # output size is: B x L x V (where L is truncated lengths
        # which are different for different batch)
        return torch.cat([_.unsqueeze(1) for _ in outputs], 1), \
               torch.cat([_.unsqueeze(1) for _ in sample_seq], 1), \
               torch.cat([_.unsqueeze(1) for _ in sample_logprobs], 1), \
               svo_out, svo_it, svo_out.gather(2, svo_it.unsqueeze(2)).squeeze(2)

    def sample(self, feats, bfeats, pos, opt={}):
        sample_max = opt.get('sample_max', 1)
        beam_size = opt.get('beam_size', 1)
        temperature = opt.get('temperature', 1.0)
        expand_feat = opt.get('expand_feat', 0)

        svo_out, svo_it = self._svo_step(feats, bfeats, expand_feat=expand_feat)
        if beam_size > 1:
            return (*self.sample_beam(feats, bfeats, pos, opt)), svo_out, svo_it

        fc_feats = self.feat_pool(feats)
        if expand_feat == 1:
            fc_feats = self.feat_expander(fc_feats)
        batch_size = fc_feats.size(0)
        state = self.init_hidden(batch_size)

        seq = []
        seqLogprobs = []

        unfinished = fc_feats.data.new(batch_size).fill_(1).byte()

        # -- if <image feature> is input at the first step, use index -1
        start_i = -1 if self.model_type == 'standard' else 0
        end_i = self.seq_length - 1

        for token_idx in range(start_i, end_i):
            if token_idx == -1:
                xt = fc_feats
            else:
                if token_idx == 0:  # input <bos>
                    it = fc_feats.data.new(batch_size).long().fill_(self.bos_index)
                elif sample_max == 1:
                    # output here is a Tensor, because we don't use backprop
                    sampleLogprobs, it = torch.max(logprobs.data, 1)
                    it = it.view(-1).long()
                else:
                    if temperature == 1.0:
                        # fetch prev distribution: shape Nx(M+1)
                        prob_prev = torch.exp(logprobs.data).cpu()
                    else:
                        # scale logprobs by temperature
                        prob_prev = torch.exp(torch.div(logprobs.data, temperature)).cpu()
                    it = torch.multinomial(prob_prev, 1).cuda()
                    # gather the logprobs at sampled positions
                    sampleLogprobs = logprobs.gather(1, Variable(it, requires_grad=False))
                    # and flatten indices for downstream processing
                    it = it.view(-1).long()

                lan_cont = self.embed(torch.cat((svo_it[:, 1:2], it.unsqueeze(1)), 1))
                hid_cont = state[0].transpose(0, 1).expand(lan_cont.shape[0], 2, state[0].shape[2])
                alpha = self.att_layer(torch.tanh(self.l2a_layer(lan_cont) + self.h2a_layer(hid_cont)))
                alpha = F.softmax(alpha, dim=1).transpose(1, 2)
                xt = torch.matmul(alpha, lan_cont).squeeze(1)

            if token_idx >= 1:
                unfinished = unfinished * (it > 0)

                it = it * unfinished.type_as(it)
                seq.append(it)
                seqLogprobs.append(sampleLogprobs.view(-1))

                # requires EOS token = 0
                if unfinished.sum() == 0:
                    break

            if self.model_type == 'standard':
                output, state = self.core(xt, state)
            else:
                if self.model_type == 'manet':
                    fc_feats = self.manet(fc_feats, state[0])
                output, state = self.core(torch.cat([xt, fc_feats], 1), state)

            logprobs = F.log_softmax(self.logit(output), dim=1)
        return torch.cat([_.unsqueeze(1) for _ in seq], 1), torch.cat([_.unsqueeze(1) for _ in seqLogprobs],
                                                                      1), svo_out, svo_it

    def sample_beam(self, feats, bfeats, pos, opt={}):
        """
        modified from https://github.com/ruotianluo/self-critical.pytorch
        """
        beam_size = opt.get('beam_size', 5)
        fc_feats = self.feat_pool(feats)
        svo_out, svo_it = self._svo_step(feats, bfeats, expand_feat=0)
        batch_size = fc_feats.size(0)

        seq = torch.LongTensor(self.seq_length, batch_size).zero_()
        seqLogprobs = torch.FloatTensor(self.seq_length, batch_size)
        # lets process every image independently for now, for simplicity

        self.done_beams = [[] for _ in range(batch_size)]
        for k in range(batch_size):
            state = self.init_hidden(beam_size)
            fc_feats_k = fc_feats[k].expand(beam_size, self.video_encoding_size)
            svo_it_k = svo_it[k].expand(beam_size, 3)
            # pos_k = pos[(k-1)*20].expand(beam_size, 3)

            beam_seq = torch.LongTensor(self.seq_length, beam_size).zero_()
            beam_seq_logprobs = torch.FloatTensor(self.seq_length, beam_size).zero_()
            # running sum of logprobs for each beam
            beam_logprobs_sum = torch.zeros(beam_size)

            # -- if <image feature> is input at the first step, use index -1
            start_i = -1 if self.model_type == 'standard' else 0
            end_i = self.seq_length - 1

            for token_idx in range(start_i, end_i):
                if token_idx == -1:
                    xt = fc_feats_k
                elif token_idx == 0:  # input <bos>
                    it = fc_feats.data.new(
                        beam_size).long().fill_(self.bos_index)
                    xt = self.embed(Variable(it, requires_grad=False))
                else:
                    """perform a beam merge. that is,
                    for every previous beam we now many new possibilities to branch out
                    we need to resort our beams to maintain the loop invariant of keeping
                    the top beam_size most likely sequences."""
                    logprobsf = logprobs.float()  # lets go to CPU for more efficiency in indexing operations
                    # sorted array of logprobs along each previous beam (last
                    # true = descending)
                    ys, ix = torch.sort(logprobsf, 1, True)
                    candidates = []
                    cols = min(beam_size, ys.size(1))
                    rows = beam_size
                    if token_idx == 1:  # at first time step only the first beam is active
                        rows = 1
                    for c in range(cols):
                        for q in range(rows):
                            # compute logprob of expanding beam q with word in
                            # (sorted) position c
                            local_logprob = ys[q, c]
                            candidate_logprob = beam_logprobs_sum[q] + local_logprob
                            candidates.append(
                                {'c': ix.data[q, c], 'q': q, 'p': candidate_logprob.item(), 'r': local_logprob.item()})
                    candidates = sorted(candidates, key=lambda x: -x['p'])

                    # construct new beams
                    new_state = [_.clone() for _ in state]
                    if token_idx > 1:
                        # well need these as reference when we fork beams
                        # around
                        beam_seq_prev = beam_seq[:token_idx - 1].clone()
                        beam_seq_logprobs_prev = beam_seq_logprobs[:token_idx - 1].clone()

                    for vix in range(beam_size):
                        v = candidates[vix]
                        # fork beam index q into index vix
                        if token_idx > 1:
                            beam_seq[:token_idx - 1, vix] = beam_seq_prev[:, v['q']]
                            beam_seq_logprobs[:token_idx - 1, vix] = beam_seq_logprobs_prev[:, v['q']]

                        # rearrange recurrent states
                        for state_ix in range(len(new_state)):
                            # copy over state in previous beam q to new beam at
                            # vix
                            new_state[state_ix][
                                0, vix] = state[state_ix][
                                0, v['q']]  # dimension one is time step

                        # append new end terminal at the end of this beam
                        # c'th word is the continuation
                        beam_seq[token_idx - 1, vix] = v['c']
                        beam_seq_logprobs[
                            token_idx - 1, vix] = v['r']  # the raw logprob here
                        # the new (sum) logprob along this beam
                        beam_logprobs_sum[vix] = v['p']

                        if v['c'] == 0 or token_idx == self.seq_length - 2:
                            # END token special case here, or we reached the end.
                            # add the beam to a set of done beams
                            if token_idx > 1:
                                ppl = np.exp(-beam_logprobs_sum[vix] / (token_idx - 1))
                            else:
                                ppl = 10000
                            self.done_beams[k].append({'seq': beam_seq[:, vix].clone(),
                                                       'logps': beam_seq_logprobs[:, vix].clone(),
                                                       'p': beam_logprobs_sum[vix],
                                                       'ppl': ppl
                                                       })

                    # encode as vectors
                    it = Variable(beam_seq[token_idx - 1].cuda())
                    if self.pass_all_svo:
                        lan_cont = self.embed(
                            torch.cat((svo_it_k[:, 0:1], svo_it_k[:, 1:2], svo_it_k[:, 2:3], it.unsqueeze(1)), 1))
                        hid_cont = state[0].transpose(0, 1).expand(lan_cont.shape[0], 4, state[0].shape[2])
                    else:
                        lan_cont = self.embed(torch.cat((svo_it_k[:, 1:2], it.unsqueeze(1)), 1))
                        hid_cont = state[0].transpose(0, 1).expand(lan_cont.shape[0], 2, state[0].shape[2])
                    alpha = self.att_layer(torch.tanh(self.l2a_layer(lan_cont) + self.h2a_layer(hid_cont)))
                    alpha = F.softmax(alpha, dim=1).transpose(1, 2)
                    xt = torch.matmul(alpha, lan_cont).squeeze(1)

                if token_idx >= 1:
                    state = new_state

                if self.model_type == 'standard':
                    output, state = self.core(xt, state)
                else:
                    if self.model_type == 'manet':
                        fc_feats_k = self.manet(fc_feats_k, state[0])
                    output, state = self.core(torch.cat([xt, fc_feats_k], 1), state)

                logprobs = F.log_softmax(self.logit(output), dim=1)

            # self.done_beams[k] = sorted(self.done_beams[k], key=lambda x: -x['p'])
            self.done_beams[k] = sorted(self.done_beams[k], key=lambda x: x['ppl'])

            # the first beam has highest cumulative score
            seq[:, k] = self.done_beams[k][0]['seq']
            seqLogprobs[:, k] = self.done_beams[k][0]['logps']

        return seq.transpose(0, 1), seqLogprobs.transpose(0, 1)

class CaptionModelConcepts(nn.Module):
    """
    A concepts captioning model
    """

    def __init__(self, opt):
        super(CaptionModelConcepts, self).__init__()
        self.vocab_size = opt.vocab_size
        self.bfeat_dims = opt.bfeat_dims
        self.feat_dims = opt.feat_dims
        self.num_feats = len(self.feat_dims)

        self.textual_encoding_size = opt.input_encoding_size
        self.visual_encoding_size = opt.input_encoding_size
        self.ct_layers = 1
        self.ct_heads = 1

        self.rnn_type = opt.rnn_type
        self.rnn_size = opt.rnn_size
        self.att_size = opt.att_size

        assert self.rnn_size == self.textual_encoding_size, print(self.rnn_size, self.textual_encoding_size)

        self.num_layers = opt.num_layers
        self.drop_prob_lm = opt.drop_prob_lm
        self.seq_length = opt.seq_length
        self.seq_per_img = opt.train_seq_per_img
        self.model_type = opt.model_type
        self.pass_all_svo = opt.pass_all_svo
        self.n_concepts =  3 # opt.n_concepts # todo fix
        self.bos_index = 1  # index of the <bos> token
        self.ss_prob = 0
        self.mixer_from = 0
        self.attention_record = list()


        self.embed = nn.Embedding(self.vocab_size, self.textual_encoding_size)  # word embedding layer (1-hot -> enc)
        self.logit = nn.Linear(self.textual_encoding_size, self.vocab_size)  # logit embedding layer (enc -> vocab enc)
        self.dropout = nn.Dropout(self.drop_prob_lm)

        # (S,V,O,past-word + hid_state) attention
        self.l2a_layer = nn.Linear(self.textual_encoding_size, self.att_size)
        self.h2a_layer = nn.Linear(self.rnn_size, self.att_size)
        self.att_layer = nn.Linear(self.att_size, 1)

        self.init_weights()
        if self.model_type == 'standard':
            self.feat_pool = FeatPool(self.feat_dims[0:1], self.visual_encoding_size, self.drop_prob_lm)
        else:
            self.feat_pool = FeatPool(self.feat_dims, self.visual_encoding_size, self.drop_prob_lm)

            # encode the visual features (linear>relu>dropout)
            self.global_encoders = list()
            for feat_dim in self.feat_dims:
                self.global_encoders.append(nn.Sequential(nn.Linear(feat_dim, self.visual_encoding_size), nn.ReLU(), nn.Dropout(self.drop_prob_lm)))
            self.global_encoders = nn.ModuleList(self.global_encoders)

            # encode the box features 1024 -> 512 and 4 -> 512 (linear>relu>dropout)
            self.box_encoder = FeatPool(self.bfeat_dims, int(self.visual_encoding_size/2), self.drop_prob_lm, SQUEEZE=False)  # TODO replace with new box encoder

            # self.embed_txt = nn.Sequential(nn.Linear(self.textual_encoding_size, self.concept_transformer_hidden_size), nn.ReLU(), nn.Dropout(self.drop_prob_lm))
            # self.embed_vis = nn.Sequential(nn.Linear(self.visual_encoding_size, self.concept_transformer_hidden_size), nn.ReLU(), nn.Dropout(self.drop_prob_lm))

            concept_encoder_layer = nn.TransformerEncoderLayer(d_model=self.visual_encoding_size, nhead=self.ct_heads,
                                                               dim_feedforward=self.visual_encoding_size, dropout=self.drop_prob_lm)
            self.concept_encoder = nn.TransformerEncoder(concept_encoder_layer, num_layers=self.ct_layers)

            concept_decoder_layer = nn.TransformerDecoderLayer(d_model=self.visual_encoding_size, nhead=self.ct_heads,
                                                               dim_feedforward=self.textual_encoding_size, dropout=self.drop_prob_lm)
            self.concept_decoder = nn.TransformerDecoder(concept_decoder_layer, num_layers=self.ct_layers)

        self.feat_expander = FeatExpander(self.seq_per_img)

        opt.video_encoding_size = self.visual_encoding_size * self.num_feats
        self.core = RNNUnit(opt)  # the caption generation rnn LSTM(512) with input size 2048

        if self.model_type == 'manet':
            self.manet = MANet(self.video_encoding_size, self.rnn_size, self.num_feats)

    def set_ss_prob(self, p):
        self.ss_prob = p

    def set_mixer_from(self, t):
        """Set values of mixer_from
        if mixer_from > 0 then start MIXER training
        i.e:
        from t = 0 -> t = mixer_from -1: use XE training
        from t = mixer_from -> end: use RL training
        """
        self.mixer_from = t

    def set_seq_per_img(self, x):
        self.seq_per_img = x
        self.feat_expander.set_n(x)

    def init_weights(self):
        initrange = 0.1
        self.embed.weight.data.uniform_(-initrange, initrange)
        self.logit.bias.data.fill_(0)
        self.logit.weight.data.uniform_(-initrange, initrange)

    def init_hidden(self, batch_size):
        weight = next(self.parameters()).data

        if self.rnn_type == 'lstm':
            return (Variable(weight.new(self.num_layers, batch_size, self.rnn_size).zero_()),
                    Variable(weight.new(self.num_layers, batch_size, self.rnn_size).zero_()))
        else:
            return Variable(weight.new(self.num_layers, batch_size, self.rnn_size).zero_())

    def concept_generator(self, feats, bfeats, pos=None, expand_feat=0):

        # encode all of the global features into a single space
        encoded_global_feats = list()
        for global_feat, global_encoder in zip(feats, self.global_encoders):
            encoded_global_feats.append(global_encoder(global_feat))

        # encode the boxes into a similar space [cat(enc(1024>512), enc(4>512))]
        encoded_boxes = self.box_encoder(bfeats)

        # concat the box features to the global features
        visual_features = torch.cat(encoded_global_feats + [encoded_boxes], dim=-2)

        # concepts_emb = self.embed_txt(self.embed(pos))
        # visual_features = self.embed_vis(combined_features)

        #### ENCODER ####
        encoded_features = self.concept_encoder(visual_features.permute(1, 0, 2))  # change to (time, batch, channel)
        encoded_features = self.feat_expander(encoded_features.permute(1, 0, 2))  # change to (batch, time, channel)
        encoded_features = encoded_features.permute(1, 0, 2)  # change to (time, batch, channel)
        #### END ENCODER ####

        #### DECODER ####
        # embed the concepts
        if self.training and pos is not None:
            concept_embeddings = self.embed(pos)
            concept_embeddings = concept_embeddings.permute(1,0,2) # change to (time, batch, channel)
            assert self.n_concepts == concept_embeddings.size(0), print(self.n_concepts, concept_embeddings.size(0))
            concept_embeddings = F.pad(concept_embeddings, (0, 0, 0, 0, 1, 0), "constant", 0)  # prepend with zero pad for first word 'our <bos> persay'
            concept_embeddings = concept_embeddings[:-1]  # remove the last concept
            assert encoded_features.shape[-1] == concept_embeddings.shape[-1], print(encoded_features.shape[-1], concept_embeddings.shape[-1])
            tgt_mask = nn.Transformer.generate_square_subsequent_mask(None, self.n_concepts).cuda()
            out = self.concept_decoder(concept_embeddings, encoded_features, tgt_mask=tgt_mask)   # out is target shp
        else:  # auto-regressive prediction at inference
            concept_embeddings = torch.zeros((self.n_concepts+1, encoded_features.size(1), self.textual_encoding_size)).cuda()
            for i in range(self.n_concepts):
                decoder_input = concept_embeddings[:i+1]
                tgt_mask = nn.Transformer.generate_square_subsequent_mask(None, i+1).cuda()
                decoder_output = self.concept_decoder(decoder_input, encoded_features, tgt_mask=tgt_mask)
                concept_embeddings[i+1] = decoder_output[-1]
            out = concept_embeddings[1:] # remove the zero <bos>
        # generate a concept
        out = out.permute(1, 0, 2) # change back to (batch, concepts, channels)

        #### END DECODER ####

        concept_prob = F.log_softmax(self.logit(out), dim=-1)
        concept_idx = F.softmax(self.logit(out), dim=-1).argmax(-1)


        return concept_prob, concept_idx

    def forward(self, feats, bfeats, seq, pos):
        fc_feats = self.feat_pool(feats)
        fc_feats = self.feat_expander(fc_feats)

        # get the svo features and vocab indexs
        svo_out, svo_it = self.concept_generator(feats, bfeats, pos)

        ########### RNN ###########
        batch_size = fc_feats.size(0)
        state = self.init_hidden(batch_size)
        outputs = []
        sample_seq = []
        sample_logprobs = []

        # -- if <image feature> is input at the first step, use index -1
        # -- the <eos> token is not used for training
        start_i = -1 if self.model_type == 'standard' else 0
        end_i = seq.size(1) - 1

        for token_idx in range(start_i, end_i):
            if token_idx == -1:  # initially set xt as global feats
                xt = fc_feats  # todo was (544,1024) could encode 1024->textual_encoding_size
                xt = torch.zeros((fc_feats.size(0), self.textual_encoding_size)).cuda()  # todo init set as zeros (544,512)
            else:
                # token_idx = 0 corresponding to the <BOS> token
                # (already encoded in seq)

                if self.training and token_idx >= 1 and self.ss_prob > 0.0:
                    sample_prob = fc_feats.data.new(batch_size).uniform_(0, 1)
                    sample_mask = sample_prob < self.ss_prob
                    if sample_mask.sum() == 0:
                        it = seq[:, token_idx].clone()
                    else:
                        sample_ind = sample_mask.nonzero().view(-1)
                        it = seq[:, token_idx].data.clone()
                        # fetch prev distribution: shape Nx(M+1)
                        prob_prev = torch.exp(outputs[-1].data)
                        sample_ind_tokens = torch.multinomial(prob_prev, 1).view(-1).index_select(0, sample_ind)
                        it.index_copy_(0, sample_ind, sample_ind_tokens)
                        it = Variable(it, requires_grad=False)
                elif self.training and self.mixer_from > 0 and token_idx >= self.mixer_from:
                    prob_prev = torch.exp(outputs[-1].data)
                    it = torch.multinomial(prob_prev, 1).view(-1)
                    it = Variable(it, requires_grad=False)
                else:
                    it = seq[:, token_idx].clone()

                if token_idx >= 1:
                    # store the seq and its logprobs
                    sample_seq.append(it.data)
                    logprobs = outputs[-1].gather(1, it.unsqueeze(1))
                    sample_logprobs.append(logprobs.view(-1))

                # break if all the sequences end, which requires EOS token = 0
                if it.data.sum() == 0:
                    break

                # get word embedding for the verb, concat with last pred word (it, rep as vocab index)
                if self.training:
                    if self.pass_all_svo:
                        lan_cont = self.embed(torch.cat((pos, it.unsqueeze(1)),1))
                    else:
                        lan_cont = self.embed(torch.cat((pos[:, 1:2], it.unsqueeze(1)), 1))  # (bs * seq_per_img, 2, 512)
                else:
                    if self.pass_all_svo:
                        lan_cont = self.embed(torch.cat((svo_it, it.unsqueeze(1)),1))
                    else:
                        lan_cont = self.embed(torch.cat((svo_it[:, 1:2], it.unsqueeze(1)), 1))

                if self.pass_all_svo:
                    hid_cont = state[0].transpose(0, 1).expand(lan_cont.shape[0], 4, state[0].shape[2])  # (bs * seq_per_img, 4, 512)
                else:
                    hid_cont = state[0].transpose(0, 1).expand(lan_cont.shape[0], 2, state[0].shape[2])  # (bs * seq_per_img, 2, 512)
                # calculate attention on encodings of the verb embedding and the RNN hidden state
                alpha = self.att_layer(torch.tanh(self.l2a_layer(lan_cont) + self.h2a_layer(hid_cont)))  # (bs * seq_per_img, 2, 1)
                alpha = F.softmax(alpha, dim=1).transpose(1, 2)  # (bs * seq_per_img, 1, 2)
                # apply the attention to the verb word embedding and the hidden layer emb
                xt = torch.matmul(alpha, lan_cont).squeeze(1)

            # generate next word
            if self.model_type == 'standard':
                output, state = self.core(xt, state)
            else:
                if self.model_type == 'manet':
                    fc_feats = self.manet(fc_feats, state[0])
                output, state = self.core(torch.cat([xt, fc_feats], 1), state)

            # generate the word softmax
            if token_idx >= 0:
                output = F.log_softmax(self.logit(self.dropout(output)), dim=1)
                outputs.append(output)

        # only returns outputs of seq input
        # output size is: B x L x V (where L is truncated lengths
        # which are different for different batch)
        return torch.cat([_.unsqueeze(1) for _ in outputs], 1), \
               torch.cat([_.unsqueeze(1) for _ in sample_seq], 1), \
               torch.cat([_.unsqueeze(1) for _ in sample_logprobs], 1), \
               svo_out, svo_it, svo_out.gather(2, svo_it.unsqueeze(2)).squeeze(2)

    def sample(self, feats, bfeats, pos, opt={}):
        sample_max = opt.get('sample_max', 1)
        beam_size = opt.get('beam_size', 1)
        temperature = opt.get('temperature', 1.0)
        expand_feat = opt.get('expand_feat', 0)

        svo_out, svo_it = self.concept_generator(feats, bfeats, expand_feat=expand_feat)
        if beam_size > 1:
            return (*self.sample_beam(feats, bfeats, pos, opt)), svo_out, svo_it

        fc_feats = self.feat_pool(feats)
        if expand_feat == 1:
            fc_feats = self.feat_expander(fc_feats)
        batch_size = fc_feats.size(0)
        state = self.init_hidden(batch_size)

        seq = []
        seqLogprobs = []

        unfinished = fc_feats.data.new(batch_size).fill_(1).byte()

        # -- if <image feature> is input at the first step, use index -1
        start_i = -1 if self.model_type == 'standard' else 0
        end_i = self.seq_length - 1

        for token_idx in range(start_i, end_i):
            if token_idx == -1:
                xt = fc_feats  # todo was (544,1024) could encode 1024->textual_encoding_size
                xt = torch.zeros((fc_feats.size(0), self.textual_encoding_size)).cuda()  # todo init set as zeros (544,512)
            else:
                if token_idx == 0:  # input <bos>
                    it = fc_feats.data.new(batch_size).long().fill_(self.bos_index)
                elif sample_max == 1:
                    # output here is a Tensor, because we don't use backprop
                    sampleLogprobs, it = torch.max(logprobs.data, 1)
                    it = it.view(-1).long()
                else:
                    if temperature == 1.0:
                        # fetch prev distribution: shape Nx(M+1)
                        prob_prev = torch.exp(logprobs.data).cpu()
                    else:
                        # scale logprobs by temperature
                        prob_prev = torch.exp(torch.div(logprobs.data, temperature)).cpu()
                    it = torch.multinomial(prob_prev, 1).cuda()
                    # gather the logprobs at sampled positions
                    sampleLogprobs = logprobs.gather(1, Variable(it, requires_grad=False))
                    # and flatten indices for downstream processing
                    it = it.view(-1).long()

                lan_cont = self.embed(torch.cat((svo_it[:, 1:2], it.unsqueeze(1)), 1))
                hid_cont = state[0].transpose(0, 1).expand(lan_cont.shape[0], 2, state[0].shape[2])
                alpha = self.att_layer(torch.tanh(self.l2a_layer(lan_cont) + self.h2a_layer(hid_cont)))
                alpha = F.softmax(alpha, dim=1).transpose(1, 2)
                xt = torch.matmul(alpha, lan_cont).squeeze(1)

            if token_idx >= 1:
                unfinished = unfinished * (it > 0)

                it = it * unfinished.type_as(it)
                seq.append(it)
                seqLogprobs.append(sampleLogprobs.view(-1))

                # requires EOS token = 0
                if unfinished.sum() == 0:
                    break

            if self.model_type == 'standard':
                output, state = self.core(xt, state)
            else:
                if self.model_type == 'manet':
                    fc_feats = self.manet(fc_feats, state[0])
                output, state = self.core(torch.cat([xt, fc_feats], 1), state)

            logprobs = F.log_softmax(self.logit(output), dim=1)
        return torch.cat([_.unsqueeze(1) for _ in seq], 1), torch.cat([_.unsqueeze(1) for _ in seqLogprobs],
                                                                      1), svo_out, svo_it

    def sample_beam(self, feats, bfeats, pos, opt={}):
        """
        modified from https://github.com/ruotianluo/self-critical.pytorch
        """
        beam_size = opt.get('beam_size', 5)
        fc_feats = self.feat_pool(feats)
        svo_out, svo_it = self.concept_generator(feats, bfeats, expand_feat=0)
        batch_size = fc_feats.size(0)

        seq = torch.LongTensor(self.seq_length, batch_size).zero_()
        seqLogprobs = torch.FloatTensor(self.seq_length, batch_size)
        # lets process every image independently for now, for simplicity

        self.done_beams = [[] for _ in range(batch_size)]
        for k in range(batch_size):
            state = self.init_hidden(beam_size)
            fc_feats_k = fc_feats[k].expand(beam_size, self.visual_encoding_size*self.num_feats)
            svo_it_k = svo_it[k].expand(beam_size, 3)
            # pos_k = pos[(k - 1) * 20].expand(beam_size, 3)

            beam_seq = torch.LongTensor(self.seq_length, beam_size).zero_()
            beam_seq_logprobs = torch.FloatTensor(self.seq_length, beam_size).zero_()
            # running sum of logprobs for each beam
            beam_logprobs_sum = torch.zeros(beam_size)

            # -- if <image feature> is input at the first step, use index -1
            start_i = -1 if self.model_type == 'standard' else 0
            end_i = self.seq_length - 1

            for token_idx in range(start_i, end_i):
                if token_idx == -1:
                    xt = fc_feats_k  # todo was (544,1024) could encode 1024->textual_encoding_size
                    xt = torch.zeros((fc_feats_k.size(0), self.textual_encoding_size)).cuda()  # todo init set as zeros (544,512)
                elif token_idx == 0:  # input <bos>
                    it = fc_feats.data.new(beam_size).long().fill_(self.bos_index)
                    xt = self.embed(Variable(it, requires_grad=False))
                else:
                    """perform a beam merge. that is,
                    for every previous beam we now many new possibilities to branch out
                    we need to resort our beams to maintain the loop invariant of keeping
                    the top beam_size most likely sequences."""
                    logprobsf = logprobs.float()  # lets go to CPU for more efficiency in indexing operations
                    # sorted array of logprobs along each previous beam (last
                    # true = descending)
                    ys, ix = torch.sort(logprobsf, 1, True)
                    candidates = []
                    cols = min(beam_size, ys.size(1))
                    rows = beam_size
                    if token_idx == 1:  # at first time step only the first beam is active
                        rows = 1
                    for c in range(cols):
                        for q in range(rows):
                            # compute logprob of expanding beam q with word in
                            # (sorted) position c
                            local_logprob = ys[q, c]
                            candidate_logprob = beam_logprobs_sum[q] + local_logprob
                            candidates.append(
                                {'c': ix.data[q, c], 'q': q, 'p': candidate_logprob.item(), 'r': local_logprob.item()})
                    candidates = sorted(candidates, key=lambda x: -x['p'])

                    # construct new beams
                    new_state = [_.clone() for _ in state]
                    if token_idx > 1:
                        # well need these as reference when we fork beams
                        # around
                        beam_seq_prev = beam_seq[:token_idx - 1].clone()
                        beam_seq_logprobs_prev = beam_seq_logprobs[:token_idx - 1].clone()

                    for vix in range(beam_size):
                        v = candidates[vix]
                        # fork beam index q into index vix
                        if token_idx > 1:
                            beam_seq[:token_idx - 1, vix] = beam_seq_prev[:, v['q']]
                            beam_seq_logprobs[:token_idx - 1, vix] = beam_seq_logprobs_prev[:, v['q']]

                        # rearrange recurrent states
                        for state_ix in range(len(new_state)):
                            # copy over state in previous beam q to new beam at
                            # vix
                            new_state[state_ix][
                                0, vix] = state[state_ix][
                                0, v['q']]  # dimension one is time step

                        # append new end terminal at the end of this beam
                        # c'th word is the continuation
                        beam_seq[token_idx - 1, vix] = v['c']
                        beam_seq_logprobs[token_idx - 1, vix] = v['r']  # the raw logprob here
                        # the new (sum) logprob along this beam
                        beam_logprobs_sum[vix] = v['p']

                        if v['c'] == 0 or token_idx == self.seq_length - 2:
                            # END token special case here, or we reached the end.
                            # add the beam to a set of done beams
                            if token_idx > 1:
                                ppl = np.exp(-beam_logprobs_sum[vix] / (token_idx - 1))
                            else:
                                ppl = 10000
                            self.done_beams[k].append({'seq': beam_seq[:, vix].clone(),
                                                       'logps': beam_seq_logprobs[:, vix].clone(),
                                                       'p': beam_logprobs_sum[vix],
                                                       'ppl': ppl
                                                       })

                    # encode as vectors
                    it = Variable(beam_seq[token_idx - 1].cuda())
                    if self.pass_all_svo:
                        lan_cont = self.embed(
                            torch.cat((svo_it_k[:, 0:1], svo_it_k[:, 1:2], svo_it_k[:, 2:3], it.unsqueeze(1)), 1))
                        hid_cont = state[0].transpose(0, 1).expand(lan_cont.shape[0], 4, state[0].shape[2])
                    else:
                        lan_cont = self.embed(torch.cat((svo_it_k[:, 1:2], it.unsqueeze(1)), 1))
                        hid_cont = state[0].transpose(0, 1).expand(lan_cont.shape[0], 2, state[0].shape[2])
                    alpha = self.att_layer(torch.tanh(self.l2a_layer(lan_cont) + self.h2a_layer(hid_cont)))
                    alpha = F.softmax(alpha, dim=1).transpose(1, 2)
                    xt = torch.matmul(alpha, lan_cont).squeeze(1)

                if token_idx >= 1:
                    state = new_state

                if self.model_type == 'standard':
                    output, state = self.core(xt, state)
                else:
                    if self.model_type == 'manet':
                        fc_feats_k = self.manet(fc_feats_k, state[0])
                    output, state = self.core(torch.cat([xt, fc_feats_k], 1), state)

                logprobs = F.log_softmax(self.logit(output), dim=1)

            # self.done_beams[k] = sorted(self.done_beams[k], key=lambda x: -x['p'])
            self.done_beams[k] = sorted(self.done_beams[k], key=lambda x: x['ppl'])

            # the first beam has highest cumulative score
            seq[:, k] = self.done_beams[k][0]['seq']
            seqLogprobs[:, k] = self.done_beams[k][0]['logps']

        return seq.transpose(0, 1), seqLogprobs.transpose(0, 1)