/** TanStack Query hooks. Every key includes the caller identity so caches never leak between accounts. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth, useIdentityKey } from "@/features/auth/auth-context";
import { api, type CreateResumeInput } from "@/lib/api";

export const queryKeys = {
  quota: (identity: string) => ["quota", identity] as const,
  me: (identity: string) => ["me", identity] as const,
  resumes: (identity: string) => ["resumes", identity] as const,
  resume: (identity: string, id: string) => ["resumes", identity, id] as const,
};

export function useQuota() {
  const identity = useIdentityKey();
  const { status } = useAuth();
  return useQuery({
    queryKey: queryKeys.quota(identity),
    queryFn: ({ signal }) => api.getQuota(signal),
    enabled: status !== "loading",
    staleTime: 30_000,
  });
}

export function useMe() {
  const identity = useIdentityKey();
  const { status } = useAuth();
  return useQuery({
    queryKey: queryKeys.me(identity),
    queryFn: ({ signal }) => api.getMe(signal),
    enabled: status === "signedIn",
    staleTime: 60_000,
  });
}

export function useResumes() {
  const identity = useIdentityKey();
  const { status } = useAuth();
  return useQuery({
    queryKey: queryKeys.resumes(identity),
    queryFn: ({ signal }) => api.listResumes(signal),
    enabled: status === "signedIn",
  });
}

export function useCreateResume() {
  const identity = useIdentityKey();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateResumeInput) => api.createResume(input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.resumes(identity) }),
  });
}

export function useUpdateResume() {
  const identity = useIdentityKey();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...changes }: { id: string; name?: string; isDefault?: boolean }) =>
      api.updateResume(id, changes),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.resumes(identity) }),
  });
}

export function useDeleteResume() {
  const identity = useIdentityKey();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteResume(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.resumes(identity) }),
  });
}
