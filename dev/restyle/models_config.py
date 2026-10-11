# AI 重绘的模型配置:models.json(仓库里,原作者电脑的配置)+ models.local.json(每台电脑自己的,不进仓库)合并。
# restyle.py 组节点图、setup_check.py 检查模型都读这里,换了模型只改配置文件,不改代码。
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
CORE_LOADERS = {"UNETLoader", "CLIPLoader"}   # ComfyUI 自带的加载节点;别的(如 ComfyUI-GGUF 的 UnetLoaderGGUF / CLIPLoaderGGUF)只填文件名


def load_models():
    cfg = json.load(open(os.path.join(HERE, "models.json"), encoding="utf-8-sig"))
    local = os.path.join(HERE, "models.local.json")
    if os.path.exists(local):
        cfg.update(json.load(open(local, encoding="utf-8-sig")))
    return {k: v for k, v in cfg.items() if not k.startswith("_")}


def loader_nodes(cfg):
    """三个加载节点 → (节点类名, 输入),组节点图和检查模型时共用"""
    unet = {"unet_name": cfg["diffusion_model"]}
    if cfg["unet_loader"] == "UNETLoader":
        unet["weight_dtype"] = "default"
    clip = {"clip_name": cfg["text_encoder"], "type": "qwen_image"}
    if cfg["clip_loader"] == "CLIPLoader":
        clip["device"] = "default"
    return {"unet": (cfg["unet_loader"], unet), "clip": (cfg["clip_loader"], clip), "vae": ("VAELoader", {"vae_name": cfg["vae"]})}
