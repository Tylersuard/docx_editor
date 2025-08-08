"""Training script for a 10 m tall, 80 ton robot to walk using reinforcement learning.

This script relies on PyBullet for simulation and Stable-Baselines3 for the
PPO algorithm. Every 100 training iterations, the agent's current policy is
visualized in the GUI so progress can be observed.
"""

import gym
import pybullet as p
import pybullet_data
import pybullet_envs  # noqa: F401 -- registers PyBullet envs with Gym
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.vec_env import DummyVecEnv

TARGET_HEIGHT_METERS = 10.0
TARGET_MASS_KG = 80_000.0


def make_env(gui: bool = False):
    """Create a scaled humanoid environment."""
    env = gym.make("HumanoidBulletEnv-v0", render=gui)
    env.reset()
    client = env.robot._p  # pybullet client
    robot_id = env.robot.robot_body.bodies[0]

    # scale the visual shape to reach approximately 10 meters height
    default_height = 1.8
    scale = TARGET_HEIGHT_METERS / default_height
    p.changeVisualShape(robot_id, -1, globalScaling=scale, physicsClientId=client)

    # distribute 80 tons of mass across all joints
    num_joints = p.getNumJoints(robot_id, physicsClientId=client)
    mass_per_link = TARGET_MASS_KG / max(1, num_joints)
    for j in range(-1, num_joints):
        p.changeDynamics(robot_id, j, mass=mass_per_link, physicsClientId=client)

    return env


class WalkVisualizationCallback(BaseCallback):
    """Render the agent walking every ``render_freq`` training steps."""

    def __init__(self, env_fn, render_freq: int = 100, steps: int = 1000):
        super().__init__()
        self.env_fn = env_fn
        self.render_freq = render_freq
        self.steps = steps

    def _on_step(self) -> bool:
        if self.num_timesteps % self.render_freq == 0:
            eval_env = self.env_fn(gui=True)
            obs = eval_env.reset()
            for _ in range(self.steps):
                action, _ = self.model.predict(obs, deterministic=True)
                obs, _, done, _ = eval_env.step(action)
                if done:
                    obs = eval_env.reset()
            eval_env.close()
        return True


def train(total_iterations: int = 10_000):
    """Train the PPO agent and visualize progress."""
    env = DummyVecEnv([lambda: make_env(gui=False)])
    model = PPO("MlpPolicy", env, verbose=0)
    callback = WalkVisualizationCallback(make_env, render_freq=100)
    model.learn(total_timesteps=total_iterations, callback=callback)
    model.save("tall_heavy_robot_ppo")


if __name__ == "__main__":
    train()
